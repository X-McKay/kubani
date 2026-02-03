"""
Build and deployment tools for kubani.

Provides commands for building agent images and deploying to clusters.
Uses local builds with Earthly and pushes to the local registry.
"""

import asyncio
import logging
import os
import subprocess
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

# Default local registry
DEFAULT_REGISTRY = "registry.almckay.io"


@dataclass
class BuildConfig:
    """Configuration for building an agent."""

    agent_name: str
    project_root: Path
    registry: str = DEFAULT_REGISTRY
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
        registry = self.config.registry or "registry.almckay.io"
        return f"{registry}/{self.config.agent_name}:{self.config.tag}"

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
            "dev": "kubani",
            "staging": "kubani-staging",
            "production": "kubani",
        }
        return namespaces.get(self.config.environment, "kubani")

    def _get_values_file(self) -> Path | None:
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
            "dev": "kubani",
            "staging": "kubani-staging",
            "production": "kubani",
        }.get(self.environment, "kubani")

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
            "dev": "kubani",
            "staging": "kubani-staging",
            "production": "kubani",
        }.get(self.environment, "kubani")

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


# ============================================================================
# Enhanced Deployment Automation
# ============================================================================

import time
from datetime import UTC, datetime
from enum import Enum

import httpx


class DeploymentPhase(Enum):
    """Phases of a deployment."""

    PENDING = "pending"
    TRIGGERING = "triggering"
    BUILDING = "building"
    PUSHING = "pushing"
    DEPLOYING = "deploying"
    VERIFYING = "verifying"
    COMPLETED = "completed"
    FAILED = "failed"
    ROLLED_BACK = "rolled_back"


class DeploymentTarget(Enum):
    """Deployment targets."""

    K8S_MONITOR = "k8s-monitor"
    NEWS_MONITOR = "news-monitor"
    REGISTRY = "registry"
    UI = "ui"
    ALL = "all"


@dataclass
class DeploymentStatus:
    """Status of a deployment."""

    deployment_id: str
    target: DeploymentTarget
    phase: DeploymentPhase
    version: str
    started_at: datetime
    updated_at: datetime = None
    completed_at: datetime = None
    message: str = ""
    details: dict = None
    logs: list = None

    def __post_init__(self):
        if self.updated_at is None:
            self.updated_at = datetime.now(UTC)
        if self.details is None:
            self.details = {}
        if self.logs is None:
            self.logs = []

    def to_dict(self) -> dict:
        """Convert to dictionary."""
        return {
            "deployment_id": self.deployment_id,
            "target": self.target.value,
            "phase": self.phase.value,
            "version": self.version,
            "started_at": self.started_at.isoformat(),
            "updated_at": self.updated_at.isoformat(),
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "message": self.message,
            "details": self.details,
        }


@dataclass
class DeploymentRequest:
    """Request to deploy an agent or service."""

    target: DeploymentTarget
    version: str = None  # None = latest
    force: bool = False
    skip_verification: bool = False
    dry_run: bool = False
    callback_url: str = None


class GitHubActionsClient:
    """Client for triggering GitHub Actions workflows."""

    def __init__(
        self,
        repo: str = "X-McKay/kubani",
        token: str = None,
    ):
        """Initialize the client."""
        self.repo = repo
        self.token = token or os.environ.get("GITHUB_TOKEN")
        self.api_url = f"https://api.github.com/repos/{repo}"

    async def trigger_workflow(
        self,
        workflow: str,
        ref: str = "main",
        inputs: dict = None,
    ) -> str | None:
        """
        Trigger a GitHub Actions workflow.

        Returns the workflow run ID if successful.
        """
        if not self.token:
            logger.error("GitHub token not configured")
            return None

        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.api_url}/actions/workflows/{workflow}/dispatches",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    json={
                        "ref": ref,
                        "inputs": inputs or {},
                    },
                    timeout=30.0,
                )

                if response.status_code == 204:
                    # Get the run ID from recent runs
                    await asyncio.sleep(2)  # Wait for workflow to start
                    run_id = await self._get_latest_run_id(workflow)
                    return run_id
                else:
                    logger.error(f"Failed to trigger workflow: {response.status_code}")

        except Exception as e:
            logger.error(f"Error triggering workflow: {e}")

        return None

    async def _get_latest_run_id(self, workflow: str) -> str | None:
        """Get the latest run ID for a workflow."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/actions/workflows/{workflow}/runs",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    params={"per_page": 1},
                    timeout=30.0,
                )

                if response.status_code == 200:
                    data = response.json()
                    runs = data.get("workflow_runs", [])
                    if runs:
                        return str(runs[0]["id"])

        except Exception as e:
            logger.warning(f"Failed to get latest run ID: {e}")

        return None

    async def get_workflow_status(self, run_id: str) -> dict | None:
        """Get the status of a workflow run."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.get(
                    f"{self.api_url}/actions/runs/{run_id}",
                    headers={
                        "Authorization": f"Bearer {self.token}",
                        "Accept": "application/vnd.github.v3+json",
                    },
                    timeout=30.0,
                )

                if response.status_code == 200:
                    return response.json()

        except Exception as e:
            logger.warning(f"Failed to get workflow status: {e}")

        return None


class LocalBuilder:
    """
    Builds and pushes agent images locally using Earthly.

    Uses the local registry (registry.almckay.io) instead of GitHub Actions.
    """

    def __init__(
        self,
        project_root: Path = None,
        registry: str = DEFAULT_REGISTRY,
    ):
        """Initialize the local builder."""
        self.project_root = project_root or Path.cwd()
        self.registry = registry
        # Map deployment targets to Earthly targets
        self.target_map = {
            "k8s-monitor": "k8s-monitor",
            "news-monitor": "news-monitor",
            "registry": "registry",
            "ui": "ui",
        }

    def _get_version(self, target: str) -> str:
        """Get the current version from pyproject.toml or generate one."""
        import re
        from datetime import datetime

        # Try to get version from syndicate's pyproject.toml
        syndicate_pyproject = (
            self.project_root
            / "kubani"
            / "syndicates"
            / target.replace("-", "_")
            / "pyproject.toml"
        )
        if syndicate_pyproject.exists():
            content = syndicate_pyproject.read_text()
            match = re.search(r'version\s*=\s*["\']([^"\']+)["\']', content)
            if match:
                return match.group(1)

        # Fall back to timestamp-based version
        return datetime.now().strftime("%Y%m%d.%H%M%S")

    def _get_git_sha(self) -> str:
        """Get the current git commit SHA."""
        try:
            result = subprocess.run(
                ["git", "rev-parse", "--short", "HEAD"],
                cwd=self.project_root,
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode == 0:
                return result.stdout.strip()
        except Exception:
            pass
        return "unknown"

    def build_and_push(
        self,
        target: str,
        version: str = None,
        stream_output: bool = True,
    ) -> tuple[bool, str]:
        """
        Build and push an image using Earthly.

        Args:
            target: The deployment target (k8s-monitor, news-monitor, etc.)
            version: Version tag (auto-generated if not provided)
            stream_output: Whether to stream build output

        Returns:
            Tuple of (success, image_tag)
        """
        earthly_target = self.target_map.get(target)
        if not earthly_target:
            logger.error(f"Unknown target: {target}")
            return False, ""

        version = version or self._get_version(target)
        git_sha = self._get_git_sha()
        image_tag = f"{version}-{git_sha}"

        if stream_output:
            print(f"   Building {target} with tag {image_tag}...")

        # Build using Earthly with push
        cmd = [
            "earthly",
            "--push",
            f"+{earthly_target}-push",
            f"--VERSION={image_tag}",
        ]

        try:
            if stream_output:
                # Stream output directly to console
                result = subprocess.run(
                    cmd,
                    cwd=self.project_root,
                    timeout=600,  # 10 minute timeout
                )
            else:
                result = subprocess.run(
                    cmd,
                    cwd=self.project_root,
                    capture_output=True,
                    text=True,
                    timeout=600,
                )

            if result.returncode != 0:
                if not stream_output and hasattr(result, "stderr"):
                    logger.error(f"Build failed: {result.stderr}")
                return False, ""

            if stream_output:
                print(f"   Successfully built and pushed {self.registry}/{target}:{image_tag}")

            return True, image_tag

        except subprocess.TimeoutExpired:
            logger.error("Build timed out")
            return False, ""
        except FileNotFoundError:
            logger.error(
                "Earthly not found. Install with: brew install earthly or see https://earthly.dev/get-earthly"
            )
            return False, ""
        except Exception as e:
            logger.error(f"Build error: {e}")
            return False, ""

    def build_all(
        self,
        version: str = None,
        stream_output: bool = True,
    ) -> dict[str, tuple[bool, str]]:
        """
        Build and push all targets.

        Returns:
            Dict mapping target name to (success, image_tag)
        """
        results = {}
        for target in self.target_map:
            results[target] = self.build_and_push(target, version, stream_output)
        return results


class GitOpsUpdater:
    """Updates GitOps manifests with new image tags."""

    def __init__(self, project_root: Path = None):
        """Initialize the updater."""
        self.project_root = project_root or Path.cwd()
        self.gitops_path = self.project_root / "infrastructure" / "gitops" / "apps" / "ai-agents"

    def update_manifest(
        self,
        target: str,
        image_tag: str,
        git_sha: str = None,
        stream_output: bool = True,
    ) -> bool:
        """
        Update the deployment manifest with a new image tag.

        Args:
            target: The deployment target (k8s-monitor, news-monitor, etc.)
            image_tag: The new image tag
            git_sha: The git commit SHA
            stream_output: Whether to print status

        Returns:
            True if successful
        """
        import re

        manifest_path = self.gitops_path / target / "deployment.yaml"
        if not manifest_path.exists():
            logger.error(f"Manifest not found: {manifest_path}")
            return False

        content = manifest_path.read_text()

        # Update the image tag
        # Pattern: image: registry.almckay.io/target:VERSION
        pattern = rf"(image:\s*{re.escape(DEFAULT_REGISTRY)}/{re.escape(target)}:)[^\s]+"
        new_content = re.sub(pattern, rf"\g<1>{image_tag}", content)

        # Update AGENT_VERSION env var if present
        new_content = re.sub(
            r'(name:\s*AGENT_VERSION\s+value:\s*")[^"]+(")',
            rf"\g<1>{image_tag}\2",
            new_content,
        )

        # Update AGENT_IMAGE_TAG env var if present
        new_content = re.sub(
            r'(name:\s*AGENT_IMAGE_TAG\s+value:\s*")[^"]+(")',
            rf"\g<1>{image_tag}\2",
            new_content,
        )

        # Update AGENT_GIT_SHA env var if present and git_sha provided
        if git_sha:
            new_content = re.sub(
                r'(name:\s*AGENT_GIT_SHA\s+value:\s*")[^"]+(")',
                rf"\g<1>{git_sha}\2",
                new_content,
            )

        if content != new_content:
            manifest_path.write_text(new_content)
            if stream_output:
                print(f"   Updated {manifest_path.relative_to(self.project_root)}")
            return True
        else:
            if stream_output:
                print(f"   No changes needed for {target}")
            return True


class ClusterDeploymentController:
    """
    Cluster-side deployment controller.

    This runs inside the cluster and handles:
    - Receiving deployment requests
    - Applying GitOps changes
    - Monitoring rollouts
    - Reporting status
    """

    def __init__(
        self,
        registry_url: str,
        namespace: str = "ai-agents",
    ):
        """Initialize the controller."""
        self.registry_url = registry_url
        self.namespace = namespace
        self._active_deployments: dict = {}

    async def deploy(self, request: DeploymentRequest) -> DeploymentStatus:
        """
        Execute a deployment.

        Steps:
        1. Validate request
        2. Update GitOps manifests (if needed)
        3. Apply changes via kubectl/ArgoCD
        4. Monitor rollout
        5. Verify health
        6. Report status
        """
        deployment_id = f"deploy-{int(time.time())}"
        status = DeploymentStatus(
            deployment_id=deployment_id,
            target=request.target,
            phase=DeploymentPhase.PENDING,
            version=request.version or "latest",
            started_at=datetime.now(UTC),
        )
        self._active_deployments[deployment_id] = status

        try:
            # Phase 1: Triggering
            status.phase = DeploymentPhase.TRIGGERING
            status.message = "Initiating deployment"
            await self._report_status(status)

            if request.dry_run:
                status.phase = DeploymentPhase.COMPLETED
                status.message = "Dry run completed"
                status.completed_at = datetime.now(UTC)
                return status

            # Phase 2: Deploying
            status.phase = DeploymentPhase.DEPLOYING
            status.message = "Applying Kubernetes manifests"
            await self._report_status(status)

            deploy_success = await self._apply_deployment(request)
            if not deploy_success:
                status.phase = DeploymentPhase.FAILED
                status.message = "Failed to apply deployment"
                return status

            # Phase 3: Verifying
            if not request.skip_verification:
                status.phase = DeploymentPhase.VERIFYING
                status.message = "Verifying deployment health"
                await self._report_status(status)

                verify_success = await self._verify_deployment(request)
                if not verify_success:
                    status.phase = DeploymentPhase.FAILED
                    status.message = "Health verification failed"

                    # Attempt rollback
                    if await self._rollback(request):
                        status.phase = DeploymentPhase.ROLLED_BACK
                        status.message = "Deployment failed, rolled back"

                    return status

            # Success
            status.phase = DeploymentPhase.COMPLETED
            status.message = "Deployment successful"
            status.completed_at = datetime.now(UTC)

        except Exception as e:
            status.phase = DeploymentPhase.FAILED
            status.message = f"Deployment error: {e}"
            logger.error(f"Deployment failed: {e}")

        await self._report_status(status)
        return status

    async def _apply_deployment(self, request: DeploymentRequest) -> bool:
        """Apply the deployment using kubectl."""
        target_map = {
            DeploymentTarget.K8S_MONITOR: "k8s-monitor",
            DeploymentTarget.NEWS_MONITOR: "news-monitor",
            DeploymentTarget.REGISTRY: "registry",
            DeploymentTarget.UI: "ui",
        }

        if request.target == DeploymentTarget.ALL:
            targets = list(target_map.values())
        else:
            targets = [target_map.get(request.target, request.target.value)]

        for target in targets:
            try:
                # Restart deployment to pick up new image
                result = subprocess.run(
                    [
                        "kubectl",
                        "rollout",
                        "restart",
                        f"deployment/{target}",
                        "-n",
                        self.namespace,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    logger.error(f"Failed to restart {target}: {result.stderr}")
                    return False

                # Wait for rollout
                result = subprocess.run(
                    [
                        "kubectl",
                        "rollout",
                        "status",
                        f"deployment/{target}",
                        "-n",
                        self.namespace,
                        "--timeout=300s",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=330,
                )

                if result.returncode != 0:
                    logger.error(f"Rollout failed for {target}: {result.stderr}")
                    return False

            except subprocess.TimeoutExpired:
                logger.error(f"Timeout waiting for {target} rollout")
                return False
            except Exception as e:
                logger.error(f"Error deploying {target}: {e}")
                return False

        return True

    async def _verify_deployment(self, request: DeploymentRequest) -> bool:
        """Verify deployment health."""
        # Give pods time to start
        await asyncio.sleep(10)

        target_map = {
            DeploymentTarget.K8S_MONITOR: ("k8s-monitor", 8080),
            DeploymentTarget.NEWS_MONITOR: ("news-monitor", 8080),
            DeploymentTarget.REGISTRY: ("registry", 8000),
            DeploymentTarget.UI: ("ui", 3000),
        }

        if request.target == DeploymentTarget.ALL:
            targets = list(target_map.items())
        else:
            targets = [(request.target, target_map.get(request.target))]

        for target, info in targets:
            if not info:
                continue

            service, port = info

            # Check pod status
            try:
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "pods",
                        "-n",
                        self.namespace,
                        "-l",
                        f"app={service}",
                        "-o",
                        "jsonpath={.items[*].status.phase}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )

                phases = result.stdout.split()
                if not all(p == "Running" for p in phases):
                    logger.warning(f"Not all {service} pods are running: {phases}")
                    return False

            except Exception as e:
                logger.error(f"Error checking {service} pods: {e}")
                return False

        return True

    async def _rollback(self, request: DeploymentRequest) -> bool:
        """Rollback a failed deployment."""
        target_map = {
            DeploymentTarget.K8S_MONITOR: "k8s-monitor",
            DeploymentTarget.NEWS_MONITOR: "news-monitor",
            DeploymentTarget.REGISTRY: "registry",
            DeploymentTarget.UI: "ui",
        }

        if request.target == DeploymentTarget.ALL:
            targets = list(target_map.values())
        else:
            targets = [target_map.get(request.target, request.target.value)]

        success = True
        for target in targets:
            try:
                result = subprocess.run(
                    [
                        "kubectl",
                        "rollout",
                        "undo",
                        f"deployment/{target}",
                        "-n",
                        self.namespace,
                    ],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )

                if result.returncode != 0:
                    logger.error(f"Failed to rollback {target}: {result.stderr}")
                    success = False

            except Exception as e:
                logger.error(f"Error rolling back {target}: {e}")
                success = False

        return success

    async def _report_status(self, status: DeploymentStatus) -> None:
        """Report deployment status to registry."""
        try:
            async with httpx.AsyncClient() as client:
                await client.post(
                    f"{self.registry_url}/api/v1/deployments/status",
                    json=status.to_dict(),
                    timeout=10.0,
                )
        except Exception as e:
            logger.warning(f"Failed to report status: {e}")


class DeploymentOrchestrator:
    """
    Orchestrates deployments from the CLI.

    Handles:
    - Local builds using Earthly
    - Pushing to local registry (registry.almckay.io)
    - Updating GitOps manifests
    - Triggering Kubernetes rollouts
    - Streaming status updates
    """

    def __init__(
        self,
        project_root: Path = None,
        registry: str = DEFAULT_REGISTRY,
        namespace: str = "ai-agents",
    ):
        """Initialize the orchestrator."""
        self.project_root = project_root or Path.cwd()
        self.registry = registry
        self.namespace = namespace
        self.builder = LocalBuilder(self.project_root, registry)
        self.gitops = GitOpsUpdater(self.project_root)

    async def deploy(
        self,
        target: str,
        version: str = None,
        force: bool = False,
        skip_verification: bool = False,
        dry_run: bool = False,
        stream_output: bool = True,
        skip_build: bool = False,
    ) -> DeploymentStatus:
        """
        Execute a deployment using local builds.

        Args:
            target: What to deploy (k8s-monitor, news-monitor, all, etc.)
            version: Version/tag to deploy (None = auto-generate)
            force: Force deployment even if no changes
            skip_verification: Skip health verification
            dry_run: Don't actually deploy
            stream_output: Stream status updates to console
            skip_build: Skip the build step (use existing images)

        Returns:
            Final deployment status
        """
        # Parse target
        try:
            deploy_target = DeploymentTarget(target)
        except ValueError:
            deploy_target = DeploymentTarget.ALL

        started_at = datetime.now(UTC)
        deployment_id = f"deploy-{int(time.time())}"

        if stream_output:
            print(f"Deploying {target}...")

        # Determine targets to build/deploy
        if deploy_target == DeploymentTarget.ALL:
            targets = ["k8s-monitor", "news-monitor"]
        else:
            targets = [target]

        image_tags = {}
        git_sha = self.builder._get_git_sha()

        # Step 1: Build and push images locally
        if not skip_build:
            if stream_output:
                print("Building and pushing to local registry...")

            for t in targets:
                if dry_run:
                    if stream_output:
                        print(f"   [dry-run] Would build {t}")
                    image_tags[t] = version or "dry-run"
                else:
                    success, image_tag = self.builder.build_and_push(t, version, stream_output)
                    if not success:
                        return DeploymentStatus(
                            deployment_id=deployment_id,
                            target=deploy_target,
                            phase=DeploymentPhase.FAILED,
                            version=version or "unknown",
                            started_at=started_at,
                            message=f"Failed to build {t}",
                        )
                    image_tags[t] = image_tag
        else:
            if stream_output:
                print("Skipping build (using existing images)...")
            # Use provided version or try to detect current version
            for t in targets:
                image_tags[t] = version or "latest"

        # Step 2: Update GitOps manifests
        if stream_output:
            print("Updating GitOps manifests...")

        for t in targets:
            if dry_run:
                if stream_output:
                    print(f"   [dry-run] Would update manifest for {t} to {image_tags[t]}")
            else:
                self.gitops.update_manifest(t, image_tags[t], git_sha, stream_output)

        # Step 3: Trigger Kubernetes rollout
        if stream_output:
            print("Triggering Kubernetes rollout...")

        if dry_run:
            if stream_output:
                print("   [dry-run] Would restart deployments")
            return DeploymentStatus(
                deployment_id=deployment_id,
                target=deploy_target,
                phase=DeploymentPhase.COMPLETED,
                version=list(image_tags.values())[0] if image_tags else "dry-run",
                started_at=started_at,
                completed_at=datetime.now(UTC),
                message="Dry run completed",
            )

        for t in targets:
            success = await self._rollout_restart(t, stream_output)
            if not success and not force:
                return DeploymentStatus(
                    deployment_id=deployment_id,
                    target=deploy_target,
                    phase=DeploymentPhase.FAILED,
                    version=image_tags.get(t, "unknown"),
                    started_at=started_at,
                    message=f"Failed to restart {t}",
                )

        # Step 4: Verify deployment health
        if not skip_verification:
            if stream_output:
                print("Verifying deployment health...")

            for t in targets:
                success = await self._verify_rollout(t, stream_output)
                if not success:
                    if stream_output:
                        print(f"   Verification failed for {t}, attempting rollback...")
                    await self._rollback(t, stream_output)
                    return DeploymentStatus(
                        deployment_id=deployment_id,
                        target=deploy_target,
                        phase=DeploymentPhase.ROLLED_BACK,
                        version=image_tags.get(t, "unknown"),
                        started_at=started_at,
                        message=f"Deployment of {t} failed verification, rolled back",
                    )

        # Success
        final_version = list(image_tags.values())[0] if image_tags else "unknown"
        if stream_output:
            print(f"Deployment completed successfully ({final_version})")

        return DeploymentStatus(
            deployment_id=deployment_id,
            target=deploy_target,
            phase=DeploymentPhase.COMPLETED,
            version=final_version,
            started_at=started_at,
            completed_at=datetime.now(UTC),
            message="Deployment successful",
        )

    async def _rollout_restart(self, target: str, stream_output: bool) -> bool:
        """Restart a deployment to pick up new images."""
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "rollout",
                    "restart",
                    f"deployment/{target}",
                    "-n",
                    self.namespace,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"Failed to restart {target}: {result.stderr}")
                return False

            if stream_output:
                print(f"   Restarted deployment/{target}")

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout restarting {target}")
            return False
        except Exception as e:
            logger.error(f"Error restarting {target}: {e}")
            return False

    async def _verify_rollout(self, target: str, stream_output: bool) -> bool:
        """Wait for rollout to complete and verify health."""
        try:
            if stream_output:
                print(f"   Waiting for {target} rollout...")

            result = subprocess.run(
                [
                    "kubectl",
                    "rollout",
                    "status",
                    f"deployment/{target}",
                    "-n",
                    self.namespace,
                    "--timeout=300s",
                ],
                capture_output=True,
                text=True,
                timeout=330,
            )

            if result.returncode != 0:
                logger.error(f"Rollout failed for {target}: {result.stderr}")
                return False

            # Give pods time to fully start
            await asyncio.sleep(5)

            # Verify pods are running
            result = subprocess.run(
                [
                    "kubectl",
                    "get",
                    "pods",
                    "-n",
                    self.namespace,
                    "-l",
                    f"app.kubernetes.io/name={target}",
                    "-o",
                    "jsonpath={.items[*].status.phase}",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            phases = result.stdout.split()
            if not phases:
                # Try alternative label
                result = subprocess.run(
                    [
                        "kubectl",
                        "get",
                        "pods",
                        "-n",
                        self.namespace,
                        "-l",
                        f"app={target}",
                        "-o",
                        "jsonpath={.items[*].status.phase}",
                    ],
                    capture_output=True,
                    text=True,
                    timeout=30,
                )
                phases = result.stdout.split()

            if not all(p == "Running" for p in phases):
                logger.warning(f"Not all {target} pods are Running: {phases}")
                return False

            if stream_output:
                print(f"   {target} is healthy")

            return True

        except subprocess.TimeoutExpired:
            logger.error(f"Timeout waiting for {target} rollout")
            return False
        except Exception as e:
            logger.error(f"Error verifying {target}: {e}")
            return False

    async def _rollback(self, target: str, stream_output: bool) -> bool:
        """Rollback a failed deployment."""
        try:
            result = subprocess.run(
                [
                    "kubectl",
                    "rollout",
                    "undo",
                    f"deployment/{target}",
                    "-n",
                    self.namespace,
                ],
                capture_output=True,
                text=True,
                timeout=60,
            )

            if result.returncode != 0:
                logger.error(f"Failed to rollback {target}: {result.stderr}")
                return False

            if stream_output:
                print(f"   Rolled back {target}")

            return True

        except Exception as e:
            logger.error(f"Error rolling back {target}: {e}")
            return False


# CLI integration
async def deploy_command(
    target: str,
    version: str = None,
    force: bool = False,
    skip_verification: bool = False,
    dry_run: bool = False,
    skip_build: bool = False,
) -> int:
    """
    CLI command for deployment.

    Builds locally with Earthly, pushes to local registry, and deploys.

    Returns exit code (0 = success).
    """
    orchestrator = DeploymentOrchestrator()
    status = await orchestrator.deploy(
        target=target,
        version=version,
        force=force,
        skip_verification=skip_verification,
        dry_run=dry_run,
        skip_build=skip_build,
        stream_output=True,
    )

    return 0 if status.phase == DeploymentPhase.COMPLETED else 1
