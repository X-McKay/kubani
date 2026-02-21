"""
Tests for Nexus Dockerfile builds.

Validates that Gateway and Orchestrator Dockerfiles build successfully
and produce working container images.

Requirements: 17.1, 17.2
"""

import subprocess
from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


@pytest.fixture
def cleanup_images():
    """Cleanup test images after tests."""
    images_to_cleanup = []

    yield images_to_cleanup

    # Cleanup
    for image in images_to_cleanup:
        try:
            subprocess.run(
                ["docker", "rmi", "-f", image],
                capture_output=True,
                timeout=30,
            )
        except Exception:
            pass  # Best effort cleanup


class TestGatewayDockerfile:
    """Tests for Gateway Dockerfile (Requirement 17.1)."""

    def test_gateway_dockerfile_exists(self, project_root):
        """Verify Gateway Dockerfile exists."""
        dockerfile = project_root / "kubani" / "nexus" / "gateway" / "Dockerfile"
        assert dockerfile.exists(), "Gateway Dockerfile not found"

    def test_gateway_dockerfile_has_correct_python_version(self, project_root):
        """Verify Gateway Dockerfile uses Python 3.12."""
        dockerfile = project_root / "kubani" / "nexus" / "gateway" / "Dockerfile"
        content = dockerfile.read_text()

        # Check for Python 3.12
        assert "python:3.12" in content, "Dockerfile should use Python 3.12"
        assert "python:3.11" not in content, "Dockerfile should not use Python 3.11"

    def test_gateway_dockerfile_has_non_root_user(self, project_root):
        """Verify Gateway Dockerfile creates non-root user."""
        dockerfile = project_root / "kubani" / "nexus" / "gateway" / "Dockerfile"
        content = dockerfile.read_text()

        # Check for user creation
        assert "useradd" in content, "Dockerfile should create a user"
        assert "USER appuser" in content, "Dockerfile should switch to appuser user"

    def test_gateway_dockerfile_exposes_port(self, project_root):
        """Verify Gateway Dockerfile exposes port 8000."""
        dockerfile = project_root / "kubani" / "nexus" / "gateway" / "Dockerfile"
        content = dockerfile.read_text()

        # Check for exposed port
        assert "EXPOSE 8000" in content, "Dockerfile should expose port 8000"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_gateway_dockerfile_builds(self, project_root, cleanup_images):
        """
        Test that Gateway Dockerfile builds successfully.

        Validates: Requirements 17.1

        This is a slow integration test that actually builds the Docker image.
        """
        dockerfile = project_root / "kubani" / "nexus" / "gateway" / "Dockerfile"
        image_tag = "kubani-nexus-gateway:test"
        cleanup_images.append(image_tag)

        # Build the image
        result = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                "-t",
                image_tag,
                str(project_root),
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for build
        )

        # Check build succeeded
        assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"

        # Verify image was created
        verify_result = subprocess.run(
            ["docker", "images", "-q", image_tag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert verify_result.stdout.strip(), f"Image {image_tag} not found after build"


class TestOrchestratorDockerfile:
    """Tests for Orchestrator Dockerfile (Requirement 17.2)."""

    def test_orchestrator_dockerfile_exists(self, project_root):
        """Verify Orchestrator Dockerfile exists."""
        dockerfile = project_root / "kubani" / "nexus" / "orchestrator" / "Dockerfile"
        assert dockerfile.exists(), "Orchestrator Dockerfile not found"

    def test_orchestrator_dockerfile_has_correct_python_version(self, project_root):
        """Verify Orchestrator Dockerfile uses Python 3.12."""
        dockerfile = project_root / "kubani" / "nexus" / "orchestrator" / "Dockerfile"
        content = dockerfile.read_text()

        # Check for Python 3.12
        assert "python:3.12" in content, "Dockerfile should use Python 3.12"
        assert "python:3.11" not in content, "Dockerfile should not use Python 3.11"

    def test_orchestrator_dockerfile_has_non_root_user(self, project_root):
        """Verify Orchestrator Dockerfile creates non-root user."""
        dockerfile = project_root / "kubani" / "nexus" / "orchestrator" / "Dockerfile"
        content = dockerfile.read_text()

        # Check for user creation
        assert "useradd" in content, "Dockerfile should create a user"
        assert "USER appuser" in content, "Dockerfile should switch to appuser user"

    @pytest.mark.slow
    @pytest.mark.integration
    def test_orchestrator_dockerfile_builds(self, project_root, cleanup_images):
        """
        Test that Orchestrator Dockerfile builds successfully.

        Validates: Requirements 17.2

        This is a slow integration test that actually builds the Docker image.
        """
        dockerfile = project_root / "kubani" / "nexus" / "orchestrator" / "Dockerfile"
        image_tag = "kubani-nexus-orchestrator:test"
        cleanup_images.append(image_tag)

        # Build the image
        result = subprocess.run(
            [
                "docker",
                "build",
                "-f",
                str(dockerfile),
                "-t",
                image_tag,
                str(project_root),
            ],
            capture_output=True,
            text=True,
            timeout=600,  # 10 minute timeout for build
        )

        # Check build succeeded
        assert result.returncode == 0, f"Docker build failed:\n{result.stderr}"

        # Verify image was created
        verify_result = subprocess.run(
            ["docker", "images", "-q", image_tag],
            capture_output=True,
            text=True,
            timeout=10,
        )
        assert verify_result.stdout.strip(), f"Image {image_tag} not found after build"
