"""Tests for activities.py - Activity functionality tests.

These tests verify specific activity functionality that isn't covered
by the workflow tests.
"""

import json

import pytest


class TestRunImprovementVersionSync:
    """Tests for version sync in run_improvement activity."""

    @pytest.fixture
    def skill_dir(self, tmp_path):
        """Create a skill directory with SKILL.md and metadata.json."""
        skill_path = tmp_path / "test-skill"
        skill_path.mkdir()

        # Create SKILL.md with version 0.1.0
        skill_md = """---
name: test-skill
version: 0.1.0
description: Test skill
---

# Test Skill

Original content."""
        (skill_path / "SKILL.md").write_text(skill_md)

        # Create metadata.json with version 0.1.0
        metadata = {
            "name": "test-skill",
            "version": "0.1.0",
            "status": "development",
        }
        (skill_path / "metadata.json").write_text(json.dumps(metadata, indent=2))

        return skill_path

    def test_updates_metadata_version(self, skill_dir):
        """Verify metadata.json version is updated after improvement."""
        from unittest.mock import MagicMock, patch

        # Mock the LLMClient
        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "content": """---
name: test-skill
version: 0.2.0
description: Test skill
---

# Test Skill

Improved content.""",
            "tokens": {},
        }

        # Import and run the activity function directly (not via Temporal)
        from kubani.workflows.skill_auto.activities import run_improvement

        # Patch the LLMClient creation (imported inside the function)
        with patch("kubani_dev.llm_client.LLMClient", return_value=mock_client):
            with patch("kubani.workflows.skill_auto.activities.get_config") as mock_config:
                mock_config.return_value.llm.api_url = "http://test/v1"
                mock_config.return_value.llm.model = "test-model"

                import asyncio

                result = asyncio.run(run_improvement(str(skill_dir), "Improve accuracy"))

        # Verify improvement was successful
        assert result["improved"] is True
        assert result.get("version_updated") == "0.2.0"

        # Verify metadata.json was updated
        metadata = json.loads((skill_dir / "metadata.json").read_text())
        assert metadata["version"] == "0.2.0"

    def test_handles_missing_version_in_frontmatter(self, skill_dir):
        """Don't crash if new content has no version in frontmatter."""
        from unittest.mock import MagicMock, patch

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "content": """---
name: test-skill
description: Test skill
---

# Test Skill

No version in frontmatter.""",
            "tokens": {},
        }

        from kubani.workflows.skill_auto.activities import run_improvement

        with patch("kubani_dev.llm_client.LLMClient", return_value=mock_client):
            with patch("kubani.workflows.skill_auto.activities.get_config") as mock_config:
                mock_config.return_value.llm.api_url = "http://test/v1"
                mock_config.return_value.llm.model = "test-model"

                import asyncio

                result = asyncio.run(run_improvement(str(skill_dir), "Improve accuracy"))

        # Should still succeed, just no version update
        assert result["improved"] is True
        assert "version_updated" not in result

        # metadata.json version should be unchanged
        metadata = json.loads((skill_dir / "metadata.json").read_text())
        assert metadata["version"] == "0.1.0"

    def test_handles_missing_metadata_file(self, tmp_path):
        """Don't crash if metadata.json doesn't exist."""
        from unittest.mock import MagicMock, patch

        skill_dir = tmp_path / "test-skill"
        skill_dir.mkdir()
        (skill_dir / "SKILL.md").write_text("---\nname: test\n---\n# Test")
        # No metadata.json

        mock_client = MagicMock()
        mock_client.chat.return_value = {
            "content": """---
name: test
version: 0.2.0
---

# Test""",
            "tokens": {},
        }

        from kubani.workflows.skill_auto.activities import run_improvement

        with patch("kubani_dev.llm_client.LLMClient", return_value=mock_client):
            with patch("kubani.workflows.skill_auto.activities.get_config") as mock_config:
                mock_config.return_value.llm.api_url = "http://test/v1"
                mock_config.return_value.llm.model = "test-model"

                import asyncio

                result = asyncio.run(run_improvement(str(skill_dir), "Improve accuracy"))

        # Should still succeed, just no version update
        assert result["improved"] is True
        assert "version_updated" not in result
