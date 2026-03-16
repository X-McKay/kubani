"""Tests for the load_skill Strands tool."""

from unittest.mock import patch

import pytest


@pytest.fixture
def skills_dir(tmp_path):
    """Create a skills directory with two test skills."""
    d1 = tmp_path / "k8s" / "diagnostic" / "check-pods"
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text(
        "---\n"
        "name: check-pods\n"
        "description: Check pod health\n"
        "metadata:\n"
        "  domain: k8s\n"
        "  category: diagnostic\n"
        "---\n\n"
        "# Check Pods\n\n"
        "## Steps\n"
        "1. Get pod status\n"
        "2. Check events\n"
    )

    d2 = tmp_path / "general" / "memory" / "store-context"
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text(
        "---\n"
        "name: store-context\n"
        "description: Store context\n"
        "---\n\n"
        "# Store Context\n\nStore stuff.\n"
    )

    return tmp_path


class TestLoadSkillFromFilesystem:
    def test_loads_existing_skill(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("check-pods")

        assert "# Check Pods" in result
        assert "Get pod status" in result

    def test_returns_full_content_including_frontmatter(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("check-pods")

        assert "name: check-pods" in result

    def test_not_found_returns_error_message(self, skills_dir):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("nonexistent-skill")

        assert "not found" in result.lower()

    def test_finds_skill_by_name_not_path(self, skills_dir):
        """Should match on the 'name' field in frontmatter, not directory name."""
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=skills_dir,
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("store-context")

        assert "# Store Context" in result

    def test_nonexistent_skills_root(self, tmp_path):
        with patch(
            "kubani.nexus.tools.skill_tools.find_skills_root",
            return_value=tmp_path / "nope",
        ):
            from kubani.nexus.tools.skill_tools import _load_skill_impl

            result = _load_skill_impl("anything")

        assert "not found" in result.lower()
