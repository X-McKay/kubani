"""
Integration tests for agent skill discovery and prompt generation.

Tests that each news syndicate agent can:
1. Discover its skills based on domain/category
2. Generate proper system prompts with skills catalog
3. Generate task-specific prompts
"""

import pytest
from pathlib import Path


class TestFeedCollectorAgent:
    """Test FeedCollectorAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/collection skills."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        agent = FeedCollectorAgent()

        # Should find collection skills
        assert len(agent.skills) > 0, "Should discover at least one skill"

        # Verify skill domains and categories
        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "collection"
            ), f"Skill {skill.name} should have category 'collection'"

    def test_expected_skills(self):
        """Agent should discover expected collection skills."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        agent = FeedCollectorAgent()
        skill_names = [s.name for s in agent.skills]

        expected = ["fetch-rss-feeds", "filter-ai-relevant", "deduplicate-articles"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"

    def test_prompt_includes_skills(self):
        """System prompt should include skills catalog."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        agent = FeedCollectorAgent()
        prompt = agent.prompt

        # Should have skills section
        assert "# Available Skills" in prompt, "Prompt should include skills catalog"
        assert "fetch-rss-feeds" in prompt, "Prompt should list fetch-rss-feeds skill"

    def test_task_prompt_generation(self):
        """Should generate task-specific prompts."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        agent = FeedCollectorAgent()
        task_prompt = agent._get_task_prompt(
            feeds=[{"name": "Test", "url": "http://test.com", "category": "test"}],
            max_age_hours=12,
            filter_ai_relevant=True,
        )

        assert "12 hours" in task_prompt or "12" in task_prompt
        assert "fetch-rss-feeds" in task_prompt.lower() or "Fetch" in task_prompt


class TestContentAnalystAgent:
    """Test ContentAnalystAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/analysis skills."""
        from kubani.agents.content_analyst import ContentAnalystAgent

        agent = ContentAnalystAgent()

        assert len(agent.skills) > 0, "Should discover at least one skill"

        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "analysis"
            ), f"Skill {skill.name} should have category 'analysis'"

    def test_expected_skills(self):
        """Agent should discover expected analysis skills."""
        from kubani.agents.content_analyst import ContentAnalystAgent

        agent = ContentAnalystAgent()
        skill_names = [s.name for s in agent.skills]

        expected = ["analyze-article", "detect-trends", "identify-breaking-news"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"

    def test_prompt_includes_skills(self):
        """System prompt should include skills catalog."""
        from kubani.agents.content_analyst import ContentAnalystAgent

        agent = ContentAnalystAgent()
        prompt = agent.prompt

        assert "# Available Skills" in prompt, "Prompt should include skills catalog"
        assert "analyze-article" in prompt, "Prompt should list analyze-article skill"


class TestResearchCollectorAgent:
    """Test ResearchCollectorAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/collection skills."""
        from kubani.agents.research_collector import ResearchCollectorAgent

        agent = ResearchCollectorAgent()

        assert len(agent.skills) > 0, "Should discover at least one skill"

        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "collection"
            ), f"Skill {skill.name} should have category 'collection'"

    def test_expected_skills(self):
        """Agent should discover collection skills for research sources."""
        from kubani.agents.research_collector import ResearchCollectorAgent

        agent = ResearchCollectorAgent()
        skill_names = [s.name for s in agent.skills]

        # Research collector uses collection skills for fetching
        expected = ["fetch-arxiv-papers", "fetch-github-trending"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"


class TestResearchAnalystAgent:
    """Test ResearchAnalystAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/diagnostic skills."""
        from kubani.agents.research_analyst import ResearchAnalystAgent

        agent = ResearchAnalystAgent()

        assert len(agent.skills) > 0, "Should discover at least one skill"

        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "diagnostic"
            ), f"Skill {skill.name} should have category 'diagnostic'"

    def test_expected_skills(self):
        """Agent should discover expected diagnostic skills."""
        from kubani.agents.research_analyst import ResearchAnalystAgent

        agent = ResearchAnalystAgent()
        skill_names = [s.name for s in agent.skills]

        expected = ["analyze-arxiv-paper", "analyze-github-repo"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"

    def test_prompt_includes_skills(self):
        """System prompt should include skills catalog."""
        from kubani.agents.research_analyst import ResearchAnalystAgent

        agent = ResearchAnalystAgent()
        prompt = agent.prompt

        assert "# Available Skills" in prompt, "Prompt should include skills catalog"
        assert "analyze-arxiv-paper" in prompt, "Prompt should list analyze-arxiv-paper skill"


class TestTrendAnalystAgent:
    """Test TrendAnalystAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/diagnostic skills."""
        from kubani.agents.trend_analyst import TrendAnalystAgent

        agent = TrendAnalystAgent()

        assert len(agent.skills) > 0, "Should discover at least one skill"

        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "diagnostic"
            ), f"Skill {skill.name} should have category 'diagnostic'"

    def test_expected_skills(self):
        """Agent should discover expected diagnostic skills."""
        from kubani.agents.trend_analyst import TrendAnalystAgent

        agent = TrendAnalystAgent()
        skill_names = [s.name for s in agent.skills]

        expected = ["analyze-trends-historical"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"

    def test_prompt_includes_skills(self):
        """System prompt should include skills catalog."""
        from kubani.agents.trend_analyst import TrendAnalystAgent

        agent = TrendAnalystAgent()
        prompt = agent.prompt

        assert "# Available Skills" in prompt, "Prompt should include skills catalog"


class TestDigestPublisherAgent:
    """Test DigestPublisherAgent skill integration."""

    def test_skill_discovery(self):
        """Agent should discover news/publishing skills."""
        from kubani.agents.digest_publisher import DigestPublisherAgent

        agent = DigestPublisherAgent()

        assert len(agent.skills) > 0, "Should discover at least one skill"

        for skill in agent.skills:
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"
            assert (
                skill.category == "publishing"
            ), f"Skill {skill.name} should have category 'publishing'"

    def test_expected_skills(self):
        """Agent should discover expected publishing skills."""
        from kubani.agents.digest_publisher import DigestPublisherAgent

        agent = DigestPublisherAgent()
        skill_names = [s.name for s in agent.skills]

        expected = ["compose-digest", "publish-discord"]
        for name in expected:
            assert name in skill_names, f"Expected skill '{name}' not found"

    def test_prompt_includes_skills(self):
        """System prompt should include skills catalog."""
        from kubani.agents.digest_publisher import DigestPublisherAgent

        agent = DigestPublisherAgent()
        prompt = agent.prompt

        assert "# Available Skills" in prompt, "Prompt should include skills catalog"
        assert "compose-digest" in prompt, "Prompt should list compose-digest skill"


class TestSkillMetadataCompliance:
    """Test that all skills have proper metadata."""

    def test_all_news_skills_have_metadata(self):
        """All news skills should have metadata.kubani namespace."""
        from kubani.framework.skills import discover_kubani_skills

        skills_root = Path(__file__).parent.parent.parent / "kubani" / "skills" / "news"

        all_skills = discover_kubani_skills(skills_root)

        for skill in all_skills:
            assert skill.domain is not None, f"Skill {skill.name} missing domain"
            assert skill.category is not None, f"Skill {skill.name} missing category"
            assert skill.domain == "news", f"Skill {skill.name} should have domain 'news'"

    def test_skill_paths_exist(self):
        """All discovered skills should have valid paths."""
        from kubani.framework.skills import discover_kubani_skills

        skills_root = Path(__file__).parent.parent.parent / "kubani" / "skills" / "news"

        all_skills = discover_kubani_skills(skills_root)

        for skill in all_skills:
            assert skill.skill_path.exists(), f"Skill path missing: {skill.skill_path}"
            skill_md = skill.skill_path / "SKILL.md"
            assert skill_md.exists(), f"SKILL.md missing: {skill_md}"
