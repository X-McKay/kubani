"""Tests for skills-centric FeedCollectorAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestFeedCollectorSkills:
    """Test FeedCollectorAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """FeedCollectorAgent should inherit from SkillsOrchestrator."""
        from kubani.agents._base import SkillsOrchestrator
        from kubani.agents.feed_collector import FeedCollectorAgent

        assert issubclass(FeedCollectorAgent, SkillsOrchestrator)

    def test_discovers_collection_skills(self):
        """Agent should filter by news/collection domain and category."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.feed_collector import FeedCollectorAgent

            agent = FeedCollectorAgent()
            assert agent.SKILLS_DOMAIN == "news"
            assert agent.SKILLS_CATEGORY == "collection"

    def test_has_collect_method(self):
        """Agent should have collect() method that delegates to skills."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.feed_collector import FeedCollectorAgent

            agent = FeedCollectorAgent()
            assert hasattr(agent, "collect")
            assert callable(agent.collect)

    @pytest.mark.asyncio
    async def test_collect_generates_task_prompt(self):
        """collect() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.feed_collector import FeedCollectorAgent

            agent = FeedCollectorAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"articles": [], "stats": {}}')

            await agent.collect(max_age_hours=24)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "collect" in prompt.lower() or "fetch" in prompt.lower()
