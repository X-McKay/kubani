"""Tests for skill discovery."""


from skills_mcp.discovery import SkillDiscovery


class TestSkillDiscovery:
    """Tests for SkillDiscovery class."""

    def test_discover_all_finds_skills(self, temp_skills_dir):
        """Test that discover_all finds all SKILL.md files."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.discover_all()

        # Should find 2 skills (excluding _development)
        paths = [s.path for s in skills]
        assert "k8s/diagnostic/check-pod-health" in paths
        assert "k8s/remediation/restart-pod" in paths
        # Development skills should be found but filtered later
        assert "_development/test-skill" in paths

    def test_discover_parses_frontmatter(self, temp_skills_dir):
        """Test that frontmatter is correctly parsed."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")

        assert skill is not None
        assert skill.name == "check-pod-health"
        assert skill.version == "1.0.0"
        assert "health status" in skill.description
        assert skill.metadata.domain == "k8s"
        assert skill.metadata.category == "diagnostic"
        assert skill.metadata.requires_approval is False
        assert skill.metadata.confidence == 0.9
        assert skill.metadata.mcp_servers == ["kubernetes-mcp-server"]

    def test_discover_finds_scripts(self, temp_skills_dir):
        """Test that scripts are discovered."""
        discovery = SkillDiscovery(temp_skills_dir)
        skill = discovery.get_skill("k8s/diagnostic/check-pod-health")

        assert skill is not None
        assert "main.py" in skill.scripts

    def test_get_skill_returns_none_for_unknown(self, temp_skills_dir):
        """Test that get_skill returns None for unknown paths."""
        discovery = SkillDiscovery(temp_skills_dir)
        discovery.discover_all()

        skill = discovery.get_skill("nonexistent/skill")
        assert skill is None

    def test_filter_by_domain(self, temp_skills_dir):
        """Test filtering skills by domain."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.filter_skills(domain="k8s")

        paths = [s.path for s in skills]
        assert "k8s/diagnostic/check-pod-health" in paths
        assert "k8s/remediation/restart-pod" in paths

    def test_filter_by_category(self, temp_skills_dir):
        """Test filtering skills by category."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.filter_skills(category="diagnostic")

        paths = [s.path for s in skills]
        assert "k8s/diagnostic/check-pod-health" in paths
        assert "k8s/remediation/restart-pod" not in paths

    def test_filter_by_allowed_patterns(self, temp_skills_dir):
        """Test filtering skills by allowed glob patterns."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.filter_skills(allowed=["k8s/diagnostic/*"])

        paths = [s.path for s in skills]
        assert "k8s/diagnostic/check-pod-health" in paths
        assert "k8s/remediation/restart-pod" not in paths

    def test_filter_by_denied_patterns(self, temp_skills_dir):
        """Test filtering skills by denied glob patterns."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.filter_skills(denied=["k8s/remediation/*"])

        paths = [s.path for s in skills]
        assert "k8s/diagnostic/check-pod-health" in paths
        assert "k8s/remediation/restart-pod" not in paths

    def test_filter_excludes_development_skills(self, temp_skills_dir):
        """Test that _development skills are excluded by default."""
        discovery = SkillDiscovery(temp_skills_dir)
        skills = discovery.filter_skills()

        paths = [s.path for s in skills]
        assert "_development/test-skill" not in paths

    def test_cache_is_used(self, temp_skills_dir):
        """Test that skills are cached after first discovery."""
        discovery = SkillDiscovery(temp_skills_dir)

        # First call
        skills1 = discovery.discover_all()
        # Second call should use cache
        skills2 = discovery.discover_all()

        assert skills1 == skills2

    def test_refresh_clears_cache(self, temp_skills_dir):
        """Test that refresh clears and rebuilds cache."""
        discovery = SkillDiscovery(temp_skills_dir)

        # First discovery
        skills1 = discovery.discover_all()

        # Refresh
        skills2 = discovery.refresh()

        # Should have same skills but be freshly loaded
        assert len(skills1) == len(skills2)

    def test_nonexistent_path(self, tmp_path):
        """Test discovery with nonexistent path."""
        discovery = SkillDiscovery(tmp_path / "nonexistent")
        skills = discovery.discover_all()

        assert skills == []
