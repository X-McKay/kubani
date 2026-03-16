"""Tests for skill catalog generation."""

import re
from pathlib import Path

import pytest

from kubani.framework.skills.catalog import (
    build_catalog_xml,
    load_skills_from_filesystem,
)


@pytest.fixture
def skills_dir(tmp_path):
    """Create a minimal skills directory with three test skills."""
    # k8s skill with full metadata
    d1 = tmp_path / "k8s" / "diagnostic" / "check-pods"
    d1.mkdir(parents=True)
    (d1 / "SKILL.md").write_text(
        "---\n"
        "name: check-pods\n"
        "description: Check pod health status\n"
        "metadata:\n"
        "  domain: k8s\n"
        "  category: diagnostic\n"
        "---\n\n"
        "# Check Pods\n\nInstructions here.\n"
    )

    # general skill
    d2 = tmp_path / "general" / "memory" / "store-context"
    d2.mkdir(parents=True)
    (d2 / "SKILL.md").write_text(
        "---\n"
        "name: store-context\n"
        "description: Store conversation context in memory\n"
        "metadata:\n"
        "  domain: general\n"
        "  category: memory\n"
        "---\n\n"
        "# Store Context\n\nInstructions here.\n"
    )

    # development skill (should be filterable)
    d3 = tmp_path / "_development" / "test-skill"
    d3.mkdir(parents=True)
    (d3 / "SKILL.md").write_text(
        "---\n"
        "name: _dev-test\n"
        "description: A development test skill\n"
        "metadata:\n"
        "  domain: _development\n"
        "  category: test\n"
        "---\n\n"
        "# Dev Test\n"
    )

    return tmp_path


class TestLoadSkillsFromFilesystem:
    def test_loads_all_skills(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        assert len(skills) == 3

    def test_skill_has_name(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        names = {s["name"] for s in skills}
        assert "check-pods" in names
        assert "store-context" in names
        assert "_dev-test" in names

    def test_skill_has_description(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        for skill in skills:
            assert skill["description"], f"{skill['name']} has empty description"

    def test_skill_has_path(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        for skill in skills:
            assert "path" in skill
            assert Path(skill["path"]).exists()

    def test_nonexistent_dir_returns_empty_list(self, tmp_path):
        skills = load_skills_from_filesystem(tmp_path / "nope")
        assert skills == []

    def test_empty_dir_returns_empty_list(self, tmp_path):
        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_malformed_frontmatter_skipped(self, tmp_path):
        """A SKILL.md with bad YAML should be skipped, not crash."""
        d = tmp_path / "bad-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\n: invalid yaml [[\n---\n\n# Bad\n")

        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_no_frontmatter_skipped(self, tmp_path):
        """A SKILL.md without --- delimiters should be skipped."""
        d = tmp_path / "plain-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("# Just Markdown\n\nNo frontmatter.\n")

        skills = load_skills_from_filesystem(tmp_path)
        assert skills == []

    def test_name_falls_back_to_dirname(self, tmp_path):
        """If frontmatter has no name, use directory name."""
        d = tmp_path / "my-skill"
        d.mkdir()
        (d / "SKILL.md").write_text("---\ndescription: No name field\n---\n\n# Skill\n")

        skills = load_skills_from_filesystem(tmp_path)
        assert len(skills) == 1
        assert skills[0]["name"] == "my-skill"

    def test_skill_key_is_relative_path(self, skills_dir):
        """skill_key should be the path relative to skills root for policy matching."""
        skills = load_skills_from_filesystem(skills_dir)
        keys = {s["skill_key"] for s in skills}
        assert "k8s/diagnostic/check-pods" in keys
        assert "general/memory/store-context" in keys
        assert "_development/test-skill" in keys


class TestBuildCatalogXml:
    def test_produces_valid_xml_structure(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert xml.startswith("<available_skills>")
        assert xml.endswith("</available_skills>")

    def test_contains_skill_names(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert 'name="check-pods"' in xml
        assert 'name="store-context"' in xml

    def test_contains_descriptions(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills)
        assert "Check pod health" in xml

    def test_denied_patterns_exclude_skills(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills, denied=["_dev*"])
        assert "_dev-test" not in xml
        assert "check-pods" in xml

    def test_multiple_denied_patterns(self, skills_dir):
        skills = load_skills_from_filesystem(skills_dir)
        xml = build_catalog_xml(skills, denied=["_dev*", "check*"])
        assert "_dev-test" not in xml
        assert "check-pods" not in xml
        assert "store-context" in xml

    def test_empty_skills_list(self):
        xml = build_catalog_xml([])
        assert "<available_skills>" in xml
        assert "</available_skills>" in xml
        lines = [line for line in xml.split("\n") if line.strip()]
        assert len(lines) == 2

    def test_description_truncated_at_120_chars(self, tmp_path):
        d = tmp_path / "long-desc"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: long-desc\ndescription: " + "A" * 200 + "\n---\n\n# X\n"
        )
        skills = load_skills_from_filesystem(tmp_path)
        xml = build_catalog_xml(skills)
        match = re.search(r'name="long-desc">(.*?)</skill>', xml)
        assert match
        assert len(match.group(1)) <= 120

    def test_newlines_in_description_collapsed(self, tmp_path):
        d = tmp_path / "multiline"
        d.mkdir()
        (d / "SKILL.md").write_text(
            "---\nname: multiline\ndescription: >\n  Line one.\n  Line two.\n---\n\n# X\n"
        )
        skills = load_skills_from_filesystem(tmp_path)
        xml = build_catalog_xml(skills)
        assert "\n" not in xml.split('name="multiline">')[1].split("</skill>")[0]
