"""
Tests for GitOps integration.
"""

import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from core_agents.events import DeploymentEvent, EventType, ImagePushedEvent
from core_agents.integrations.gitops import (
    DeploymentResult,
    FluxStatus,
    GitOpsAgent,
    GitOpsConfig,
    GitOpsManager,
)


class TestGitOpsConfig:
    """Tests for GitOpsConfig."""

    def test_default_values(self):
        """Config should have sensible defaults."""
        config = GitOpsConfig()

        assert config.repo_path == "."
        assert config.registry == "registry.almckay.io"
        assert config.namespace == "ai-agents"
        assert config.manifests_base_path == "gitops/apps/ai-agents"
        assert config.flux_timeout_seconds == 300
        assert config.git_author_name == "GitOpsAgent"

    def test_custom_values(self):
        """Config should accept custom values."""
        config = GitOpsConfig(
            repo_path="/custom/path",
            registry="custom.registry.io",
            namespace="custom-ns",
        )

        assert config.repo_path == "/custom/path"
        assert config.registry == "custom.registry.io"
        assert config.namespace == "custom-ns"


class TestGitOpsManager:
    """Tests for GitOpsManager."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repo with a manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manifest directory structure
            manifest_dir = Path(tmpdir) / "gitops/apps/ai-agents/k8s-monitor"
            manifest_dir.mkdir(parents=True)

            # Create a sample deployment manifest
            manifest_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-monitor
  namespace: ai-agents
spec:
  template:
    spec:
      containers:
      - name: k8s-monitor
        image: registry.almckay.io/k8s-monitor:0.2.0-abc1234
"""
            (manifest_dir / "deployment.yaml").write_text(manifest_content)

            yield tmpdir

    @pytest.fixture
    def manager(self, temp_repo):
        """Create a GitOpsManager with temp repo."""
        config = GitOpsConfig(repo_path=temp_repo)
        return GitOpsManager(config)

    def test_get_manifest_path(self, manager, temp_repo):
        """Should construct correct manifest path."""
        path = manager.get_manifest_path("k8s-monitor")

        assert path == Path(temp_repo) / "gitops/apps/ai-agents/k8s-monitor/deployment.yaml"

    def test_get_current_image_tag(self, manager):
        """Should extract current image tag from manifest."""
        tag = manager.get_current_image_tag("k8s-monitor")

        assert tag == "0.2.0-abc1234"

    def test_get_current_image_tag_not_found(self, manager):
        """Should return None for non-existent manifest."""
        tag = manager.get_current_image_tag("non-existent")

        assert tag is None

    def test_update_image_tag(self, manager):
        """Should update image tag in manifest."""
        result = manager.update_image_tag("k8s-monitor", "0.3.0-def5678")

        assert result is True

        # Verify the change
        new_tag = manager.get_current_image_tag("k8s-monitor")
        assert new_tag == "0.3.0-def5678"

    def test_update_image_tag_preserves_format(self, manager, temp_repo):
        """Should preserve YAML formatting when updating."""
        manager.update_image_tag("k8s-monitor", "0.3.0-def5678")

        manifest_path = Path(temp_repo) / "gitops/apps/ai-agents/k8s-monitor/deployment.yaml"
        content = manifest_path.read_text()

        # Should still be valid YAML structure
        assert "apiVersion: apps/v1" in content
        assert "kind: Deployment" in content
        assert "registry.almckay.io/k8s-monitor:0.3.0-def5678" in content

    def test_update_image_tag_non_existent(self, manager):
        """Should return False for non-existent manifest."""
        result = manager.update_image_tag("non-existent", "0.3.0")

        assert result is False


class TestDeploymentResult:
    """Tests for DeploymentResult dataclass."""

    def test_success_result(self):
        """Should represent successful deployment."""
        result = DeploymentResult(
            success=True,
            agent_name="k8s-monitor",
            image_tag="0.3.0",
            commit_sha="abc1234",
            duration_seconds=45.5,
        )

        assert result.success is True
        assert result.error is None
        assert result.rolled_back is False

    def test_failure_result(self):
        """Should represent failed deployment."""
        result = DeploymentResult(
            success=False,
            agent_name="k8s-monitor",
            image_tag="0.3.0",
            error="Deployment verification failed",
            rolled_back=True,
        )

        assert result.success is False
        assert result.error == "Deployment verification failed"
        assert result.rolled_back is True


class TestFluxStatus:
    """Tests for FluxStatus dataclass."""

    def test_ready_status(self):
        """Should represent ready kustomization."""
        status = FluxStatus(
            ready=True,
            message="Applied revision main/abc1234",
            last_applied_revision="main/abc1234",
        )

        assert status.ready is True
        assert status.suspended is False

    def test_not_ready_status(self):
        """Should represent not ready kustomization."""
        status = FluxStatus(
            ready=False,
            message="Reconciliation in progress",
        )

        assert status.ready is False


class TestEventSchemas:
    """Tests for GitOps event schemas."""

    def test_image_pushed_event(self):
        """ImagePushedEvent should have required fields."""
        event = ImagePushedEvent(
            agent_name="k8s-monitor",
            new_tag="0.3.0-abc1234",
            previous_tag="0.2.0-def5678",
        )

        assert event.agent_name == "k8s-monitor"
        assert event.new_tag == "0.3.0-abc1234"
        assert event.previous_tag == "0.2.0-def5678"
        assert event.registry == "registry.almckay.io"  # Default

    def test_deployment_event(self):
        """DeploymentEvent should have required fields."""
        event = DeploymentEvent(
            agent_name="k8s-monitor",
            image_tag="0.3.0",
            namespace="ai-agents",
            duration_seconds=60.5,
        )

        assert event.agent_name == "k8s-monitor"
        assert event.image_tag == "0.3.0"
        assert event.namespace == "ai-agents"
        assert event.duration_seconds == 60.5
        assert event.error is None


class TestGitOpsAgent:
    """Tests for GitOpsAgent."""

    @pytest.fixture
    def temp_repo(self):
        """Create a temporary repo with a manifest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            manifest_dir = Path(tmpdir) / "gitops/apps/ai-agents/k8s-monitor"
            manifest_dir.mkdir(parents=True)

            manifest_content = """apiVersion: apps/v1
kind: Deployment
metadata:
  name: k8s-monitor
spec:
  template:
    spec:
      containers:
      - name: k8s-monitor
        image: registry.almckay.io/k8s-monitor:0.2.0-abc1234
"""
            (manifest_dir / "deployment.yaml").write_text(manifest_content)

            yield tmpdir

    @pytest.fixture
    def agent(self, temp_repo):
        """Create a GitOpsAgent with temp repo."""
        config = GitOpsConfig(repo_path=temp_repo)
        return GitOpsAgent(config)

    @pytest.mark.asyncio
    async def test_handle_image_pushed(self, agent):
        """Should handle image pushed event."""
        # Mock the deploy method to avoid actual git/kubectl operations
        with patch.object(agent.manager, "deploy") as mock_deploy:
            mock_deploy.return_value = DeploymentResult(
                success=True,
                agent_name="k8s-monitor",
                image_tag="0.3.0",
                commit_sha="new1234",
            )

            result = await agent.handle_image_pushed(
                {
                    "agent_name": "k8s-monitor",
                    "new_tag": "0.3.0",
                    "previous_tag": "0.2.0",
                }
            )

            assert result.success is True
            assert result.agent_name == "k8s-monitor"
            mock_deploy.assert_called_once()

    @pytest.mark.asyncio
    async def test_handle_image_pushed_publishes_events(self, agent):
        """Should publish deployment events."""
        from unittest.mock import AsyncMock

        mock_bus = MagicMock()
        mock_bus.publish = AsyncMock()

        with patch.object(agent.manager, "deploy", new_callable=AsyncMock) as mock_deploy:
            mock_deploy.return_value = DeploymentResult(
                success=True,
                agent_name="k8s-monitor",
                image_tag="0.3.0",
            )

            await agent.handle_image_pushed(
                {"agent_name": "k8s-monitor", "new_tag": "0.3.0"},
                event_bus=mock_bus,
            )

            # Should have published start and complete events
            assert mock_bus.publish.call_count == 2

            # First call should be deployment started
            first_call = mock_bus.publish.call_args_list[0]
            assert first_call[0][0] == EventType.GITOPS_DEPLOYMENT_STARTED

            # Second call should be deployment completed
            second_call = mock_bus.publish.call_args_list[1]
            assert second_call[0][0] == EventType.GITOPS_DEPLOYMENT_COMPLETED


class TestQuickDeploy:
    """Tests for quick_deploy helper."""

    @pytest.mark.asyncio
    async def test_quick_deploy(self):
        """quick_deploy should create manager and deploy."""
        with tempfile.TemporaryDirectory() as tmpdir:
            # Create manifest
            manifest_dir = Path(tmpdir) / "gitops/apps/ai-agents/test-agent"
            manifest_dir.mkdir(parents=True)
            (manifest_dir / "deployment.yaml").write_text(
                "image: registry.almckay.io/test-agent:0.1.0"
            )

            # Import here to avoid issues with module reloading
            from core_agents.integrations.gitops import quick_deploy

            # Mock the git/kubectl operations
            with patch(
                "core_agents.integrations.gitops.GitOpsManager.git_commit_and_push"
            ) as mock_git:
                mock_git.return_value = "abc1234"

                result = await quick_deploy(
                    "test-agent",
                    "0.2.0",
                    repo_path=tmpdir,
                    wait=False,
                )

                assert result.success is True
                assert result.image_tag == "0.2.0"
