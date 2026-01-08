"""
Chaos Engineering Testing Framework.

Provides utilities for:
- Applying chaos-mesh experiments
- Monitoring system health during chaos
- Waiting for chaos completion
- Verifying system recovery

Example:
    from tests.chaos.framework import ChaosTestHelper

    helper = ChaosTestHelper()

    # Apply chaos experiment
    await helper.apply_experiment("redis_failure.yaml")

    # Wait for chaos to complete
    await helper.wait_for_completion("redis-failure")

    # Verify system recovered
    assert await helper.check_agents_healthy()
"""

import asyncio
import json
import logging
import os
import subprocess
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

# Default paths
MANIFESTS_DIR = Path(__file__).parent / "manifests"
KUBECONFIG = os.environ.get("KUBECONFIG", os.path.expanduser("~/.kube/config"))


@dataclass
class ChaosExperiment:
    """Represents a chaos experiment."""

    name: str
    kind: str  # PodChaos, NetworkChaos, StressChaos
    namespace: str = "chaos-mesh"
    duration: str = "30s"
    status: str = "pending"
    manifest_path: Path | None = None


@dataclass
class AgentHealth:
    """Health status of an agent."""

    name: str
    namespace: str
    ready: bool
    restart_count: int = 0
    last_restart: str | None = None
    error_logs: list[str] = field(default_factory=list)


@dataclass
class ChaosResult:
    """Result of a chaos test."""

    experiment_name: str
    success: bool
    duration_seconds: float
    agents_crashed: list[str] = field(default_factory=list)
    recovery_time_seconds: float | None = None
    errors: list[str] = field(default_factory=list)


class ChaosTestHelper:
    """
    Helper class for chaos engineering tests.

    Provides utilities for:
    - Applying chaos experiments
    - Monitoring agent health
    - Waiting for chaos completion
    - Verifying system recovery
    """

    def __init__(
        self,
        kubeconfig: str | None = None,
        namespace: str = "ai-agents",
        chaos_namespace: str = "chaos-mesh",
        manifests_dir: Path | None = None,
    ):
        self.kubeconfig = kubeconfig or KUBECONFIG
        self.namespace = namespace
        self.chaos_namespace = chaos_namespace
        self.manifests_dir = manifests_dir or MANIFESTS_DIR
        self._env = {"KUBECONFIG": self.kubeconfig, **os.environ}

    def _run_kubectl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run kubectl command."""
        cmd = ["kubectl", *args]
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=check,
            env=self._env,
        )

    async def check_chaos_mesh_installed(self) -> bool:
        """Check if chaos-mesh is installed in the cluster."""
        try:
            result = self._run_kubectl(
                "get",
                "pods",
                "-n",
                self.chaos_namespace,
                "-l",
                "app.kubernetes.io/name=chaos-mesh",
                "-o",
                "json",
                check=False,
            )
            if result.returncode != 0:
                return False

            data = json.loads(result.stdout)
            pods = data.get("items", [])
            return len(pods) > 0
        except Exception as e:
            logger.warning(f"Failed to check chaos-mesh installation: {e}")
            return False

    def get_agent_pods(self) -> list[dict[str, Any]]:
        """Get all agent pods in the namespace."""
        try:
            result = self._run_kubectl(
                "get",
                "pods",
                "-n",
                self.namespace,
                "-o",
                "json",
            )
            data = json.loads(result.stdout)
            return data.get("items", [])
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to get agent pods: {e.stderr}")
            return []

    def check_agents_healthy(self) -> list[AgentHealth]:
        """Check health of all agents in the namespace."""
        pods = self.get_agent_pods()
        health_list = []

        for pod in pods:
            name = pod["metadata"]["name"]

            # Skip pods that are Succeeded/Completed (e.g., Jobs)
            phase = pod.get("status", {}).get("phase", "")
            if phase in ("Succeeded", "Failed"):
                continue

            # Get container statuses
            container_statuses = pod.get("status", {}).get("containerStatuses", [])
            ready = all(cs.get("ready", False) for cs in container_statuses)

            # Get restart count
            restart_count = sum(cs.get("restartCount", 0) for cs in container_statuses)

            # Check for termination reasons
            last_restart = None
            for cs in container_statuses:
                last_state = cs.get("lastState", {})
                if "terminated" in last_state:
                    terminated = last_state["terminated"]
                    last_restart = terminated.get("finishedAt")

            health_list.append(
                AgentHealth(
                    name=name,
                    namespace=self.namespace,
                    ready=ready,
                    restart_count=restart_count,
                    last_restart=last_restart,
                )
            )

        return health_list

    async def check_all_agents_healthy(self) -> bool:
        """Check if all agents are healthy."""
        health_list = self.check_agents_healthy()
        return all(h.ready for h in health_list)

    def get_agent_logs(
        self,
        agent_name: str | None = None,
        tail_lines: int = 100,
        since: str = "5m",
    ) -> str:
        """Get logs from agent pods."""
        try:
            args = ["logs", "-n", self.namespace, f"--tail={tail_lines}", f"--since={since}"]

            if agent_name:
                args.extend(["-l", f"app.kubernetes.io/name={agent_name}"])
            else:
                args.extend(["-l", "app.kubernetes.io/component=ai-agent"])

            result = self._run_kubectl(*args, check=False)
            return result.stdout
        except Exception as e:
            logger.warning(f"Failed to get logs: {e}")
            return ""

    def apply_experiment(self, experiment_file: str) -> bool:
        """Apply a chaos experiment from a manifest file."""
        manifest_path = self.manifests_dir / experiment_file

        if not manifest_path.exists():
            logger.error(f"Experiment manifest not found: {manifest_path}")
            return False

        try:
            self._run_kubectl(
                "apply",
                "-f",
                str(manifest_path),
            )
            logger.info(f"Applied chaos experiment: {experiment_file}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to apply experiment: {e.stderr}")
            return False

    def delete_experiment(self, experiment_file: str) -> bool:
        """Delete a chaos experiment."""
        manifest_path = self.manifests_dir / experiment_file

        if not manifest_path.exists():
            logger.error(f"Experiment manifest not found: {manifest_path}")
            return False

        try:
            self._run_kubectl(
                "delete",
                "-f",
                str(manifest_path),
                check=False,  # Don't fail if already deleted
            )
            logger.info(f"Deleted chaos experiment: {experiment_file}")
            return True
        except Exception as e:
            logger.warning(f"Failed to delete experiment: {e}")
            return False

    def get_experiment_status(self, name: str, kind: str = "PodChaos") -> dict[str, Any]:
        """Get the status of a chaos experiment."""
        try:
            result = self._run_kubectl(
                "get",
                kind.lower(),
                name,
                "-n",
                self.chaos_namespace,
                "-o",
                "json",
            )
            return json.loads(result.stdout)
        except subprocess.CalledProcessError:
            return {}

    async def wait_for_chaos_completion(
        self,
        name: str,
        kind: str = "PodChaos",
        timeout: int = 300,
        poll_interval: int = 5,
    ) -> bool:
        """Wait for a chaos experiment to complete."""
        start_time = time.time()

        while time.time() - start_time < timeout:
            status = self.get_experiment_status(name, kind)

            if not status:
                # Experiment might have been deleted/completed
                return True

            # Check conditions
            conditions = status.get("status", {}).get("conditions", [])
            for condition in conditions:
                if condition.get("type") == "Paused" and condition.get("status") == "True":
                    return True
                if condition.get("type") == "AllRecovered" and condition.get("status") == "True":
                    return True

            await asyncio.sleep(poll_interval)

        logger.warning(f"Timeout waiting for chaos {name} to complete")
        return False

    async def wait_for_recovery(
        self,
        timeout: int = 120,
        poll_interval: int = 5,
    ) -> float | None:
        """
        Wait for all agents to recover and return recovery time.

        Returns:
            Recovery time in seconds, or None if timeout
        """
        start_time = time.time()

        while time.time() - start_time < timeout:
            if await self.check_all_agents_healthy():
                return time.time() - start_time

            await asyncio.sleep(poll_interval)

        return None

    async def run_experiment(
        self,
        experiment_file: str,
        pre_check: bool = True,
        wait_for_completion: bool = True,
        cleanup: bool = True,
    ) -> ChaosResult:
        """
        Run a complete chaos experiment.

        Args:
            experiment_file: Name of the manifest file
            pre_check: Whether to verify agents are healthy before starting
            wait_for_completion: Whether to wait for chaos to complete
            cleanup: Whether to delete the experiment after

        Returns:
            ChaosResult with experiment outcome
        """
        start_time = time.time()
        result = ChaosResult(
            experiment_name=experiment_file,
            success=False,
            duration_seconds=0,
        )

        # Pre-check health
        if pre_check and not await self.check_all_agents_healthy():
            result.errors.append("Agents were not healthy before experiment")
            return result

        # Get initial health state
        initial_health = self.check_agents_healthy()

        # Apply experiment
        if not self.apply_experiment(experiment_file):
            result.errors.append("Failed to apply chaos experiment")
            return result

        # Wait a bit for chaos to take effect
        await asyncio.sleep(5)

        # Check for crashed agents
        mid_health = self.check_agents_healthy()
        for health in mid_health:
            initial = next((h for h in initial_health if h.name == health.name), None)
            if initial and health.restart_count > initial.restart_count:
                result.agents_crashed.append(health.name)

        # Wait for completion
        if wait_for_completion:
            # Parse experiment to get name and kind
            manifest_path = self.manifests_dir / experiment_file
            if manifest_path.exists():
                with open(manifest_path) as f:
                    manifest = yaml.safe_load(f)
                    name = manifest.get("metadata", {}).get("name", "unknown")
                    kind = manifest.get("kind", "PodChaos")

                await self.wait_for_chaos_completion(name, kind)

        # Check recovery
        recovery_time = await self.wait_for_recovery()
        result.recovery_time_seconds = recovery_time

        # Cleanup
        if cleanup:
            self.delete_experiment(experiment_file)

        result.duration_seconds = time.time() - start_time
        result.success = len(result.agents_crashed) == 0 and recovery_time is not None

        return result


# Pytest fixtures and utilities
def skip_without_chaos_mesh(helper: ChaosTestHelper):
    """Skip test if chaos-mesh is not installed."""
    import pytest

    async def check():
        return await helper.check_chaos_mesh_installed()

    if not asyncio.run(check()):
        pytest.skip("chaos-mesh not installed in cluster")


def chaos_test(func):
    """Decorator for chaos tests - ensures cleanup on failure."""
    import functools

    @functools.wraps(func)
    async def wrapper(*args, **kwargs):
        helper = ChaosTestHelper()
        try:
            return await func(*args, helper=helper, **kwargs)
        finally:
            # Ensure all experiments are cleaned up
            for manifest in MANIFESTS_DIR.glob("*.yaml"):
                helper.delete_experiment(manifest.name)

    return wrapper
