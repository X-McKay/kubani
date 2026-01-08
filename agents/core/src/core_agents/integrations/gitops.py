"""
GitOps integration for automated deployment management.

Provides utilities for:
- Updating GitOps manifests with new image tags
- Verifying Flux CD reconciliation
- Handling rollbacks on deployment failures

Example:
    from core_agents.integrations.gitops import GitOpsManager

    manager = GitOpsManager(repo_path="/path/to/kubani")

    # Update manifest and wait for deployment
    result = await manager.deploy(
        agent_name="k8s-monitor",
        new_tag="0.2.0-abc1234",
    )
"""

import asyncio
import logging
import os
import re
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GitOpsConfig(BaseModel):
    """Configuration for GitOps operations."""

    repo_path: str = Field(
        default=".",
        description="Path to the GitOps repository",
    )
    registry: str = Field(
        default="registry.almckay.io",
        description="Container registry URL",
    )
    namespace: str = Field(
        default="ai-agents",
        description="Kubernetes namespace for agents",
    )
    manifests_base_path: str = Field(
        default="gitops/apps/ai-agents",
        description="Base path to agent manifests",
    )
    kubeconfig: str = Field(
        default="~/.kube/config",
        description="Path to kubeconfig file",
    )
    flux_timeout_seconds: int = Field(
        default=300,
        description="Timeout for Flux reconciliation",
    )
    reconciliation_poll_interval: int = Field(
        default=5,
        description="Seconds between reconciliation status checks",
    )
    git_author_name: str = Field(
        default="GitOpsAgent",
        description="Git commit author name",
    )
    git_author_email: str = Field(
        default="gitops@kubani.ai",
        description="Git commit author email",
    )


@dataclass
class DeploymentResult:
    """Result of a deployment operation."""

    success: bool
    agent_name: str
    image_tag: str
    commit_sha: str | None = None
    duration_seconds: float | None = None
    error: str | None = None
    previous_tag: str | None = None
    rolled_back: bool = False


@dataclass
class FluxStatus:
    """Status of a Flux kustomization."""

    ready: bool
    message: str
    last_applied_revision: str | None = None
    suspended: bool = False


class GitOpsManager:
    """
    Manages GitOps deployment operations.

    Handles:
    - Manifest updates with new image tags
    - Git commit and push
    - Flux reconciliation verification
    - Rollback on deployment failures
    """

    def __init__(self, config: GitOpsConfig | None = None):
        self.config = config or GitOpsConfig()
        self._kubeconfig = os.path.expanduser(self.config.kubeconfig)

    def get_manifest_path(self, agent_name: str) -> Path:
        """Get the deployment manifest path for an agent."""
        return (
            Path(self.config.repo_path)
            / self.config.manifests_base_path
            / agent_name
            / "deployment.yaml"
        )

    def get_current_image_tag(self, agent_name: str) -> str | None:
        """Read the current image tag from a deployment manifest."""
        manifest_path = self.get_manifest_path(agent_name)
        if not manifest_path.exists():
            logger.warning(f"Manifest not found: {manifest_path}")
            return None

        content = manifest_path.read_text()
        # Match image: registry.almckay.io/<agent>:<tag>
        pattern = rf"image:\s*{re.escape(self.config.registry)}/{re.escape(agent_name)}:([^\s]+)"
        match = re.search(pattern, content)

        if match:
            return match.group(1)
        return None

    def update_image_tag(self, agent_name: str, new_tag: str) -> bool:
        """Update the image tag in a deployment manifest."""
        manifest_path = self.get_manifest_path(agent_name)
        if not manifest_path.exists():
            logger.error(f"Manifest not found: {manifest_path}")
            return False

        content = manifest_path.read_text()

        # Replace all occurrences of the image tag for this agent
        pattern = rf"(image:\s*{re.escape(self.config.registry)}/{re.escape(agent_name)}:)[^\s]+"
        new_content = re.sub(pattern, rf"\g<1>{new_tag}", content)

        if content == new_content:
            logger.warning(f"No changes made to {manifest_path}")
            return False

        manifest_path.write_text(new_content)
        logger.info(f"Updated {manifest_path} with tag {new_tag}")
        return True

    def _run_git(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a git command in the repo directory."""
        cmd = ["git", "-C", self.config.repo_path, *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check)

    def _run_kubectl(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a kubectl command with the configured kubeconfig."""
        env = os.environ.copy()
        env["KUBECONFIG"] = self._kubeconfig
        cmd = ["kubectl", *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)

    def _run_flux(self, *args: str, check: bool = True) -> subprocess.CompletedProcess:
        """Run a flux command with the configured kubeconfig."""
        env = os.environ.copy()
        env["KUBECONFIG"] = self._kubeconfig
        cmd = ["flux", *args]
        return subprocess.run(cmd, capture_output=True, text=True, check=check, env=env)

    def git_commit_and_push(self, agent_name: str, new_tag: str) -> str | None:
        """Commit manifest changes and push to remote."""
        manifest_path = self.get_manifest_path(agent_name)
        relative_path = manifest_path.relative_to(self.config.repo_path)

        try:
            # Stage the manifest
            self._run_git("add", str(relative_path))

            # Check if there are staged changes
            result = self._run_git("diff", "--staged", "--quiet", check=False)
            if result.returncode == 0:
                logger.warning("No changes to commit")
                return None

            # Set author info
            env = os.environ.copy()
            env["GIT_AUTHOR_NAME"] = self.config.git_author_name
            env["GIT_AUTHOR_EMAIL"] = self.config.git_author_email
            env["GIT_COMMITTER_NAME"] = self.config.git_author_name
            env["GIT_COMMITTER_EMAIL"] = self.config.git_author_email

            # Commit
            message = f"chore(gitops): deploy {agent_name}:{new_tag}"
            commit_cmd = ["git", "-C", self.config.repo_path, "commit", "-m", message]
            subprocess.run(commit_cmd, capture_output=True, text=True, check=True, env=env)

            # Get commit SHA
            result = self._run_git("rev-parse", "HEAD")
            commit_sha = result.stdout.strip()

            # Push
            self._run_git("push")

            logger.info(f"Pushed commit {commit_sha[:7]}")
            return commit_sha

        except subprocess.CalledProcessError as e:
            logger.error(f"Git operation failed: {e.stderr}")
            return None

    def get_flux_kustomization_status(self, name: str = "ai-agents") -> FluxStatus:
        """Get the status of a Flux kustomization."""
        try:
            result = self._run_flux("get", "kustomization", name, "-n", "flux-system", "-o", "json")

            import json

            data = json.loads(result.stdout)

            # Extract status conditions
            conditions = data.get("status", {}).get("conditions", [])
            ready_condition = next((c for c in conditions if c.get("type") == "Ready"), None)

            return FluxStatus(
                ready=ready_condition.get("status") == "True" if ready_condition else False,
                message=ready_condition.get("message", "Unknown")
                if ready_condition
                else "No Ready condition",
                last_applied_revision=data.get("status", {}).get("lastAppliedRevision"),
                suspended=data.get("spec", {}).get("suspend", False),
            )

        except (subprocess.CalledProcessError, json.JSONDecodeError) as e:
            logger.warning(f"Failed to get Flux status: {e}")
            return FluxStatus(ready=False, message=str(e))

    def get_deployment_image_tag(self, agent_name: str) -> str | None:
        """Get the current image tag from the running deployment."""
        try:
            result = self._run_kubectl(
                "get",
                "deployment",
                agent_name,
                "-n",
                self.config.namespace,
                "-o",
                "jsonpath={.spec.template.spec.containers[0].image}",
            )

            image = result.stdout.strip()
            if ":" in image:
                return image.split(":")[-1]
            return None

        except subprocess.CalledProcessError:
            return None

    def trigger_flux_reconciliation(self, name: str = "ai-agents") -> bool:
        """Trigger immediate Flux reconciliation."""
        try:
            self._run_flux("reconcile", "kustomization", name, "-n", "flux-system", "--with-source")
            logger.info(f"Triggered Flux reconciliation for {name}")
            return True
        except subprocess.CalledProcessError as e:
            logger.error(f"Failed to trigger reconciliation: {e.stderr}")
            return False

    async def wait_for_reconciliation(
        self,
        agent_name: str,
        expected_tag: str,
        timeout: int | None = None,
    ) -> bool:
        """Wait for Flux to reconcile and verify the deployment has the expected tag."""
        timeout = timeout or self.config.flux_timeout_seconds
        start_time = time.time()

        while time.time() - start_time < timeout:
            # Check Flux status
            status = self.get_flux_kustomization_status()

            if status.ready:
                # Verify the deployment has the expected tag
                current_tag = self.get_deployment_image_tag(agent_name)

                if current_tag == expected_tag:
                    logger.info(f"Deployment {agent_name} has expected tag {expected_tag}")
                    return True

                logger.debug(
                    f"Waiting for tag update: current={current_tag}, expected={expected_tag}"
                )

            await asyncio.sleep(self.config.reconciliation_poll_interval)

        logger.error(f"Timeout waiting for {agent_name} to deploy {expected_tag}")
        return False

    async def wait_for_rollout(self, agent_name: str, timeout: int = 120) -> bool:
        """Wait for deployment rollout to complete."""
        try:
            # Use kubectl rollout status with timeout
            env = os.environ.copy()
            env["KUBECONFIG"] = self._kubeconfig

            process = await asyncio.create_subprocess_exec(
                "kubectl",
                "rollout",
                "status",
                f"deployment/{agent_name}",
                "-n",
                self.config.namespace,
                f"--timeout={timeout}s",
                env=env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            stdout, stderr = await process.communicate()

            if process.returncode == 0:
                logger.info(f"Rollout complete for {agent_name}")
                return True
            else:
                logger.error(f"Rollout failed: {stderr.decode()}")
                return False

        except Exception as e:
            logger.error(f"Error waiting for rollout: {e}")
            return False

    def rollback(self, agent_name: str, previous_tag: str) -> bool:
        """Rollback to a previous image tag."""
        logger.info(f"Rolling back {agent_name} to {previous_tag}")

        if not self.update_image_tag(agent_name, previous_tag):
            return False

        commit_sha = self.git_commit_and_push(agent_name, f"{previous_tag} (rollback)")

        return commit_sha is not None

    async def deploy(
        self,
        agent_name: str,
        new_tag: str,
        auto_rollback: bool = True,
        wait_for_reconciliation: bool = True,
    ) -> DeploymentResult:
        """
        Deploy a new image tag for an agent.

        Args:
            agent_name: Name of the agent to deploy
            new_tag: New image tag to deploy
            auto_rollback: Whether to automatically rollback on failure
            wait_for_reconciliation: Whether to wait for Flux reconciliation

        Returns:
            DeploymentResult with deployment status
        """
        start_time = time.time()

        # Get current tag for potential rollback
        previous_tag = self.get_current_image_tag(agent_name)
        logger.info(f"Deploying {agent_name}: {previous_tag} -> {new_tag}")

        # Update manifest
        if not self.update_image_tag(agent_name, new_tag):
            return DeploymentResult(
                success=False,
                agent_name=agent_name,
                image_tag=new_tag,
                error="Failed to update manifest",
                previous_tag=previous_tag,
            )

        # Commit and push
        commit_sha = self.git_commit_and_push(agent_name, new_tag)
        if not commit_sha:
            return DeploymentResult(
                success=False,
                agent_name=agent_name,
                image_tag=new_tag,
                error="Failed to commit changes",
                previous_tag=previous_tag,
            )

        if not wait_for_reconciliation:
            return DeploymentResult(
                success=True,
                agent_name=agent_name,
                image_tag=new_tag,
                commit_sha=commit_sha,
                duration_seconds=time.time() - start_time,
                previous_tag=previous_tag,
            )

        # Trigger Flux reconciliation
        self.trigger_flux_reconciliation()

        # Wait for reconciliation
        success = await self.wait_for_reconciliation(agent_name, new_tag)

        if success:
            # Wait for rollout to complete
            success = await self.wait_for_rollout(agent_name)

        if not success and auto_rollback and previous_tag:
            logger.warning(f"Deployment failed, rolling back to {previous_tag}")
            self.rollback(agent_name, previous_tag)
            self.trigger_flux_reconciliation()
            await self.wait_for_reconciliation(agent_name, previous_tag)

            return DeploymentResult(
                success=False,
                agent_name=agent_name,
                image_tag=new_tag,
                commit_sha=commit_sha,
                duration_seconds=time.time() - start_time,
                error="Deployment failed, rolled back",
                previous_tag=previous_tag,
                rolled_back=True,
            )

        return DeploymentResult(
            success=success,
            agent_name=agent_name,
            image_tag=new_tag,
            commit_sha=commit_sha,
            duration_seconds=time.time() - start_time,
            previous_tag=previous_tag,
            error=None if success else "Deployment verification failed",
        )


class GitOpsAgent:
    """
    Agent that handles GitOps deployment automation.

    Listens for AGENT_IMAGE_PUSHED events and automatically:
    1. Updates GitOps manifests
    2. Commits and pushes changes
    3. Verifies Flux reconciliation
    4. Rolls back on failures
    5. Publishes deployment events

    Example:
        from core_agents.integrations.gitops import GitOpsAgent
        from core_agents.events import get_event_bus

        agent = GitOpsAgent()
        bus = await get_event_bus()

        # Start listening for image push events
        await agent.run(bus)
    """

    def __init__(self, config: GitOpsConfig | None = None):
        self.config = config or GitOpsConfig()
        self.manager = GitOpsManager(config)
        self._running = False

    async def handle_image_pushed(
        self,
        event_payload: dict[str, Any],
        event_bus: Any = None,
    ) -> DeploymentResult:
        """
        Handle an AGENT_IMAGE_PUSHED event.

        Args:
            event_payload: Event payload with agent_name, new_tag, etc.
            event_bus: Optional event bus for publishing events

        Returns:
            DeploymentResult with deployment status
        """
        from core_agents.events import DeploymentEvent, EventType, ImagePushedEvent

        # Parse event payload
        pushed = ImagePushedEvent(**event_payload)

        logger.info(f"Processing image push for {pushed.agent_name}:{pushed.new_tag}")

        # Publish deployment started event
        if event_bus:
            await event_bus.publish(
                EventType.GITOPS_DEPLOYMENT_STARTED,
                DeploymentEvent(
                    agent_name=pushed.agent_name,
                    image_tag=pushed.new_tag,
                ).model_dump(),
            )

        start_time = time.time()

        # Deploy
        result = await self.manager.deploy(
            agent_name=pushed.agent_name,
            new_tag=pushed.new_tag,
            auto_rollback=pushed.previous_tag is not None,
        )

        # Publish result event
        if event_bus:
            event_type = (
                EventType.GITOPS_DEPLOYMENT_COMPLETED
                if result.success
                else EventType.GITOPS_DEPLOYMENT_FAILED
            )
            await event_bus.publish(
                event_type,
                DeploymentEvent(
                    agent_name=pushed.agent_name,
                    image_tag=pushed.new_tag,
                    commit_sha=result.commit_sha,
                    error=result.error,
                    duration_seconds=time.time() - start_time,
                ).model_dump(),
            )

        return result

    async def run(self, event_bus: Any):
        """
        Start listening for image push events.

        Args:
            event_bus: Event bus to subscribe to
        """
        from core_agents.events import EventType

        self._running = True
        logger.info("GitOpsAgent started, listening for image push events")

        async for event in event_bus.subscribe(EventType.AGENT_IMAGE_PUSHED):
            if not self._running:
                break

            try:
                result = await self.handle_image_pushed(
                    event.payload,
                    event_bus,
                )

                if result.success:
                    logger.info(f"Successfully deployed {result.agent_name}:{result.image_tag}")
                else:
                    logger.error(f"Failed to deploy {result.agent_name}: {result.error}")

            except Exception as e:
                logger.exception(f"Error handling image push event: {e}")

    def stop(self):
        """Stop the agent."""
        self._running = False
        logger.info("GitOpsAgent stopping")


# Convenience function for quick deployments
async def quick_deploy(
    agent_name: str,
    new_tag: str,
    repo_path: str = ".",
    wait: bool = True,
) -> DeploymentResult:
    """
    Quick deployment helper.

    Args:
        agent_name: Agent to deploy
        new_tag: New image tag
        repo_path: Path to GitOps repo
        wait: Whether to wait for reconciliation

    Returns:
        DeploymentResult
    """
    config = GitOpsConfig(repo_path=repo_path)
    manager = GitOpsManager(config)
    return await manager.deploy(agent_name, new_tag, wait_for_reconciliation=wait)
