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


# ============================================================================
# Enhanced Deployment Automation
# ============================================================================

from enum import Enum
from datetime import datetime, UTC
import time
from typing import Callable
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
    ) -> Optional[str]:
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

    async def _get_latest_run_id(self, workflow: str) -> Optional[str]:
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

    async def get_workflow_status(self, run_id: str) -> Optional[dict]:
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
    - Triggering GitHub Actions (for builds)
    - Communicating with cluster controller
    - Streaming status updates
    - Providing user feedback
    """

    def __init__(
        self,
        github_repo: str = "X-McKay/kubani",
        registry_url: str = None,
    ):
        """Initialize the orchestrator."""
        self.github = GitHubActionsClient(github_repo)
        self.registry_url = registry_url or os.environ.get(
            "REGISTRY_URL", "http://localhost:8000"
        )

    async def deploy(
        self,
        target: str,
        version: str = None,
        force: bool = False,
        skip_verification: bool = False,
        dry_run: bool = False,
        stream_output: bool = True,
    ) -> DeploymentStatus:
        """
        Execute a deployment.

        Args:
            target: What to deploy (k8s-monitor, news-monitor, all, etc.)
            version: Version/tag to deploy (None = latest)
            force: Force deployment even if no changes
            skip_verification: Skip health verification
            dry_run: Don't actually deploy
            stream_output: Stream status updates to console

        Returns:
            Final deployment status
        """
        # Parse target
        try:
            deploy_target = DeploymentTarget(target)
        except ValueError:
            deploy_target = DeploymentTarget.ALL

        request = DeploymentRequest(
            target=deploy_target,
            version=version,
            force=force,
            skip_verification=skip_verification,
            dry_run=dry_run,
        )

        if stream_output:
            print(f"🚀 Starting deployment of {target}...")

        # Step 1: Trigger GitHub Actions for build
        if stream_output:
            print("📦 Triggering build workflow...")

        workflow_id = await self.github.trigger_workflow(
            "release.yml",
            inputs={
                "target": target,
                "version": version or "latest",
            },
        )

        if workflow_id:
            if stream_output:
                print(f"   Build workflow started: {workflow_id}")

            # Wait for build to complete
            await self._wait_for_workflow(workflow_id, stream_output)
        else:
            if stream_output:
                print("   ⚠️ Could not trigger build workflow, proceeding with existing images")

        # Step 2: Request deployment from cluster controller
        if stream_output:
            print("🔄 Requesting deployment from cluster...")

        status = await self._request_cluster_deployment(request)

        # Step 3: Monitor deployment
        if not dry_run:
            status = await self._monitor_deployment(status.deployment_id, stream_output)

        # Final status
        if stream_output:
            if status.phase == DeploymentPhase.COMPLETED:
                print(f"✅ Deployment completed successfully!")
            elif status.phase == DeploymentPhase.ROLLED_BACK:
                print(f"⚠️ Deployment failed and was rolled back")
            else:
                print(f"❌ Deployment failed: {status.message}")

        return status

    async def _wait_for_workflow(self, run_id: str, stream_output: bool) -> None:
        """Wait for a GitHub Actions workflow to complete."""
        max_wait = 600  # 10 minutes
        start = time.time()

        while time.time() - start < max_wait:
            status = await self.github.get_workflow_status(run_id)
            if not status:
                break

            current = status.get("status")
            conclusion = status.get("conclusion")

            if current == "completed":
                if stream_output:
                    if conclusion == "success":
                        print("   ✅ Build completed successfully")
                    else:
                        print(f"   ⚠️ Build completed with: {conclusion}")
                break

            await asyncio.sleep(15)

    async def _request_cluster_deployment(
        self,
        request: DeploymentRequest,
    ) -> DeploymentStatus:
        """Request deployment from the cluster controller."""
        try:
            async with httpx.AsyncClient() as client:
                response = await client.post(
                    f"{self.registry_url}/api/v1/deployments",
                    json={
                        "target": request.target.value,
                        "version": request.version,
                        "force": request.force,
                        "skip_verification": request.skip_verification,
                        "dry_run": request.dry_run,
                    },
                    timeout=30.0,
                )

                if response.status_code in (200, 201):
                    data = response.json()
                    return DeploymentStatus(
                        deployment_id=data.get("deployment_id", "unknown"),
                        target=request.target,
                        phase=DeploymentPhase(data.get("phase", "pending")),
                        version=request.version or "latest",
                        started_at=datetime.now(UTC),
                        message=data.get("message", ""),
                    )

        except Exception as e:
            logger.error(f"Failed to request deployment: {e}")

        # Return a failed status
        return DeploymentStatus(
            deployment_id="failed",
            target=request.target,
            phase=DeploymentPhase.FAILED,
            version=request.version or "latest",
            started_at=datetime.now(UTC),
            message="Failed to communicate with cluster controller",
        )

    async def _monitor_deployment(
        self,
        deployment_id: str,
        stream_output: bool,
    ) -> DeploymentStatus:
        """Monitor a deployment until completion."""
        max_wait = 600  # 10 minutes
        start = time.time()
        last_phase = None

        while time.time() - start < max_wait:
            try:
                async with httpx.AsyncClient() as client:
                    response = await client.get(
                        f"{self.registry_url}/api/v1/deployments/{deployment_id}",
                        timeout=10.0,
                    )

                    if response.status_code == 200:
                        data = response.json()
                        phase = DeploymentPhase(data.get("phase", "pending"))

                        if phase != last_phase and stream_output:
                            print(f"   {self._phase_emoji(phase)} {data.get('message', phase.value)}")
                            last_phase = phase

                        if phase in (
                            DeploymentPhase.COMPLETED,
                            DeploymentPhase.FAILED,
                            DeploymentPhase.ROLLED_BACK,
                        ):
                            return DeploymentStatus(
                                deployment_id=deployment_id,
                                target=DeploymentTarget(data.get("target", "all")),
                                phase=phase,
                                version=data.get("version", ""),
                                started_at=datetime.fromisoformat(data.get("started_at", datetime.now(UTC).isoformat())),
                                message=data.get("message", ""),
                            )

            except Exception as e:
                logger.warning(f"Error monitoring deployment: {e}")

            await asyncio.sleep(5)

        # Timeout
        return DeploymentStatus(
            deployment_id=deployment_id,
            target=DeploymentTarget.ALL,
            phase=DeploymentPhase.FAILED,
            version="",
            started_at=datetime.now(UTC),
            message="Deployment monitoring timed out",
        )

    def _phase_emoji(self, phase: DeploymentPhase) -> str:
        """Get emoji for a phase."""
        emoji_map = {
            DeploymentPhase.PENDING: "⏳",
            DeploymentPhase.TRIGGERING: "🔄",
            DeploymentPhase.BUILDING: "🔨",
            DeploymentPhase.PUSHING: "📤",
            DeploymentPhase.DEPLOYING: "🚀",
            DeploymentPhase.VERIFYING: "🔍",
            DeploymentPhase.COMPLETED: "✅",
            DeploymentPhase.FAILED: "❌",
            DeploymentPhase.ROLLED_BACK: "⏪",
        }
        return emoji_map.get(phase, "•")


# CLI integration
async def deploy_command(
    target: str,
    version: str = None,
    force: bool = False,
    skip_verification: bool = False,
    dry_run: bool = False,
) -> int:
    """
    CLI command for deployment.

    Returns exit code (0 = success).
    """
    orchestrator = DeploymentOrchestrator()
    status = await orchestrator.deploy(
        target=target,
        version=version,
        force=force,
        skip_verification=skip_verification,
        dry_run=dry_run,
        stream_output=True,
    )

    return 0 if status.phase == DeploymentPhase.COMPLETED else 1
