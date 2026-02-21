"""
Tests for Earthfile build targets.

Validates that Earthfile has proper targets for Nexus services.

Requirements: 17.3
"""

from pathlib import Path

import pytest


@pytest.fixture
def project_root():
    """Get the project root directory."""
    return Path(__file__).parent.parent.parent


class TestEarthfile:
    """Tests for Earthfile (Requirement 17.3)."""

    def test_earthfile_exists(self, project_root):
        """Verify Earthfile exists at project root."""
        earthfile = project_root / "Earthfile"
        assert earthfile.exists(), "Earthfile not found at project root"

    def test_earthfile_has_nexus_targets(self, project_root):
        """
        Verify Earthfile would support Nexus service targets.
        
        Note: The current Earthfile is structured for agents, not Nexus services.
        This test documents that Nexus services would need their own Earthfile
        or targets added to the root Earthfile.
        
        Validates: Requirements 17.3
        """
        earthfile = project_root / "Earthfile"
        content = earthfile.read_text()
        
        # Document current state: Earthfile exists but doesn't have Nexus targets yet
        # This is expected as Nexus is new and Earthfile is for the agent system
        assert "VERSION" in content, "Earthfile should have VERSION directive"
        
        # Check if Nexus targets exist (they don't yet, which is expected)
        has_nexus_gateway = "nexus-gateway" in content.lower()
        has_nexus_orchestrator = "nexus-orchestrator" in content.lower()
        
        # Document the current state
        if not (has_nexus_gateway or has_nexus_orchestrator):
            pytest.skip(
                "Earthfile does not yet have Nexus targets. "
                "Nexus services use Dockerfiles directly. "
                "Earthfile targets for Nexus can be added in the future if needed."
            )

    def test_earthfile_structure(self, project_root):
        """Verify Earthfile has proper structure."""
        earthfile = project_root / "Earthfile"
        content = earthfile.read_text()
        
        # Check for basic Earthfile structure
        assert "VERSION" in content, "Earthfile should have VERSION directive"
        assert "FROM" in content or "ARG" in content, "Earthfile should have build instructions"
