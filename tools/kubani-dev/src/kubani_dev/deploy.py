"""
Build and deployment tools for kubani-dev.

Provides commands for building agent images and deploying to clusters.
"""

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class BuildConfig:
    """Configuration for building an agent."""

    agent_name: str
    project_root: Path
    registry: str = ""
    tag: str = "latest"
    push: bool = False
    platform: str = "linux/amd64"


@dataclass
class DeployConfig:
    """Configuration for deploying an agent."""

    agent_name: str
    project_root: Path
    environment: str = "dev"  # dev, staging, production
    namespace: str = ""
    image_tag: str = "latest"
    dry_run: bool = False


class AgentBuilder:
    """
    Builds agent container images.

    Supports:
    - Docker/Podman builds
    - Multi-platform builds
    - Registry push
    """

    def __init__(self, config: BuildConfig):
        self.config = config
        self.agent_path = config.project_root / "agents" / config.agent_name

    def _get_dockerfile_path(self) -> Path:
        """Get the Dockerfile path for the agent."""
        # Check for agent-specific Dockerfile
        agent_dockerfile = self.agent_path / "Dockerfile"
        if agent_dockerfile.exists():
            return agent_dockerfile

        # Fall back to shared Dockerfile
        shared_dockerfile = self.config.project_root / "docker" / "Dockerfile.agent"
        if shared_dockerfile.exists():
            return shared_dockerfile

        raise FileNotFoundError(f"No Dockerfile found for {self.config.agent_name}")

    def _get_image_name(self) -> str:
        """Get the full image name."""
        registry = self.config.registry or "ghcr.io/x-mckay"
        return f"{registry}/kubani-{self.config.agent_name}:{self.config.tag}"

    def build(self) -> bool:
        """Build the agent image."""
        dockerfile = self._get_dockerfile_path()
        image_name = self._get_image_name()

        logger.info(f"Building {image_name}")

        cmd = [
            "docker",
            "build",
            "-t",
            image_name,
            "-f",
            str(dockerfile),
            "--build-arg",
            f"AGENT_NAME={self.config.agent_name}",
            "--platform",
            self.config.platform,
            str(self.config.project_root),
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Build failed: {result.stderr}")
                return False

            logger.info(f"Built {image_name}")

            if self.config.push:
                return self.push()

            return True

        except Exception as e:
            logger.error(f"Build error: {e}")
            return False

    def push(self) -> bool:
        """Push the image to registry."""
        image_name = self._get_image_name()

        logger.info(f"Pushing {image_name}")

        cmd = ["docker", "push", image_name]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Push failed: {result.stderr}")
                return False

            logger.info(f"Pushed {image_name}")
            return True

        except Exception as e:
            logger.error(f"Push error: {e}")
            return False


class AgentDeployer:
    """
    Deploys agents to Kubernetes clusters.

    Supports:
    - Multiple environments (dev, staging, production)
    - Helm-based deployments
    - Dry-run mode
    """

    def __init__(self, config: DeployConfig):
        self.config = config
        self.agent_path = config.project_root / "agents" / config.agent_name

    def _get_namespace(self) -> str:
        """Get the target namespace."""
        if self.config.namespace:
            return self.config.namespace

        # Default namespaces by environment
        namespaces = {
            "dev": "kubani-dev",
            "staging": "kubani-staging",
            "production": "kubani",
        }
        return namespaces.get(self.config.environment, "kubani-dev")

    def _get_values_file(self) -> Optional[Path]:
        """Get the Helm values file for the environment."""
        values_dir = self.agent_path / "deploy" / "values"

        # Environment-specific values
        env_values = values_dir / f"{self.config.environment}.yaml"
        if env_values.exists():
            return env_values

        # Default values
        default_values = values_dir / "default.yaml"
        if default_values.exists():
            return default_values

        return None

    def _get_chart_path(self) -> Path:
        """Get the Helm chart path."""
        # Agent-specific chart
        agent_chart = self.agent_path / "deploy" / "chart"
        if agent_chart.exists():
            return agent_chart

        # Shared chart
        shared_chart = self.config.project_root / "deploy" / "charts" / "agent"
        if shared_chart.exists():
            return shared_chart

        raise FileNotFoundError(f"No Helm chart found for {self.config.agent_name}")

    def deploy(self) -> bool:
        """Deploy the agent."""
        namespace = self._get_namespace()
        chart_path = self._get_chart_path()
        values_file = self._get_values_file()

        release_name = f"kubani-{self.config.agent_name}"

        logger.info(f"Deploying {release_name} to {namespace}")

        cmd = [
            "helm",
            "upgrade",
            "--install",
            release_name,
            str(chart_path),
            "--namespace",
            namespace,
            "--create-namespace",
            "--set",
            f"image.tag={self.config.image_tag}",
            "--set",
            f"agent.name={self.config.agent_name}",
        ]

        if values_file:
            cmd.extend(["-f", str(values_file)])

        if self.config.dry_run:
            cmd.append("--dry-run")

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Deploy failed: {result.stderr}")
                return False

            if self.config.dry_run:
                logger.info("Dry run output:")
                print(result.stdout)
            else:
                logger.info(f"Deployed {release_name}")

            return True

        except Exception as e:
            logger.error(f"Deploy error: {e}")
            return False

    def rollback(self, revision: int = 0) -> bool:
        """Rollback to a previous revision."""
        namespace = self._get_namespace()
        release_name = f"kubani-{self.config.agent_name}"

        logger.info(f"Rolling back {release_name}")

        cmd = [
            "helm",
            "rollback",
            release_name,
            str(revision) if revision > 0 else "",
            "--namespace",
            namespace,
        ]

        # Remove empty string if no revision specified
        cmd = [c for c in cmd if c]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                logger.error(f"Rollback failed: {result.stderr}")
                return False

            logger.info(f"Rolled back {release_name}")
            return True

        except Exception as e:
            logger.error(f"Rollback error: {e}")
            return False

    def status(self) -> dict:
        """Get deployment status."""
        namespace = self._get_namespace()
        release_name = f"kubani-{self.config.agent_name}"

        cmd = [
            "helm",
            "status",
            release_name,
            "--namespace",
            namespace,
            "-o",
            "json",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return {"status": "not_deployed", "error": result.stderr}

            import json

            return json.loads(result.stdout)

        except Exception as e:
            return {"status": "error", "error": str(e)}


class ProductionMonitor:
    """
    Monitor agent deployments in production.

    Provides real-time monitoring and alerting capabilities.
    """

    def __init__(
        self,
        agent_name: str,
        project_root: Path,
        environment: str = "production",
    ):
        self.agent_name = agent_name
        self.project_root = project_root
        self.environment = environment

    async def watch(self, callback=None) -> None:
        """Watch agent logs and metrics."""
        namespace = {
            "dev": "kubani-dev",
            "staging": "kubani-staging",
            "production": "kubani",
        }.get(self.environment, "kubani-dev")

        cmd = [
            "kubectl",
            "logs",
            "-f",
            "-l",
            f"app=kubani-{self.agent_name}",
            "-n",
            namespace,
            "--tail=100",
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

        try:
            while True:
                line = await process.stdout.readline()
                if not line:
                    break

                log_line = line.decode().strip()
                if callback:
                    callback(log_line)
                else:
                    print(log_line)

        except asyncio.CancelledError:
            process.terminate()
            await process.wait()

    def get_pods(self) -> list[dict]:
        """Get pod status for the agent."""
        namespace = {
            "dev": "kubani-dev",
            "staging": "kubani-staging",
            "production": "kubani",
        }.get(self.environment, "kubani-dev")

        cmd = [
            "kubectl",
            "get",
            "pods",
            "-l",
            f"app=kubani-{self.agent_name}",
            "-n",
            namespace,
            "-o",
            "json",
        ]

        try:
            result = subprocess.run(cmd, capture_output=True, text=True)
            if result.returncode != 0:
                return []

            import json

            data = json.loads(result.stdout)
            return data.get("items", [])

        except Exception as e:
            logger.error(f"Failed to get pods: {e}")
            return []
