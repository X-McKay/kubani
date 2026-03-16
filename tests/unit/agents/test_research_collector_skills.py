"""Tests for skills-centric ResearchCollectorAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestResearchCollectorSkills:
    """Test ResearchCollectorAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """ResearchCollectorAgent should inherit from SkillsOrchestrator."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents._base import SkillsOrchestrator
            from kubani.agents.research_collector import ResearchCollectorAgent

            assert issubclass(ResearchCollectorAgent, SkillsOrchestrator)

    def test_discovers_collection_skills(self):
        """Agent should filter by news/collection domain and category."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_collector import ResearchCollectorAgent

            agent = ResearchCollectorAgent()
            assert agent.SKILLS_DOMAIN == "news"
            assert agent.SKILLS_CATEGORY == "collection"

    def test_has_fetch_methods(self):
        """Agent should have fetch_arxiv_papers and fetch_github_trending methods."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_collector import ResearchCollectorAgent

            agent = ResearchCollectorAgent()
            assert hasattr(agent, "fetch_arxiv_papers")
            assert callable(agent.fetch_arxiv_papers)
            assert hasattr(agent, "fetch_github_trending")
            assert callable(agent.fetch_github_trending)

    @pytest.mark.asyncio
    async def test_fetch_arxiv_papers_generates_task_prompt(self):
        """fetch_arxiv_papers() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_collector import ResearchCollectorAgent

            agent = ResearchCollectorAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"papers": [], "total_fetched": 0}')

            await agent.fetch_arxiv_papers(categories=["cs.AI"], max_age_days=7)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "arxiv" in prompt.lower() or "papers" in prompt.lower()

    @pytest.mark.asyncio
    async def test_fetch_github_trending_generates_task_prompt(self):
        """fetch_github_trending() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_collector import ResearchCollectorAgent

            agent = ResearchCollectorAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"repos": [], "total_found": 0}')

            await agent.fetch_github_trending(topics=["llm"], min_stars=100)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "github" in prompt.lower() or "trending" in prompt.lower()

    @pytest.mark.asyncio
    async def test_collect_all_runs_both_fetches(self):
        """collect_all() should run both arXiv and GitHub collection."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_collector import ResearchCollectorAgent

            agent = ResearchCollectorAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"papers": [], "repos": []}')

            result = await agent.collect_all()

            # Verify result structure
            assert hasattr(result, "papers")
            assert hasattr(result, "repos")

    def test_exports_dataclasses(self):
        """Agent module should export required dataclasses."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_collector import (
                ArxivPaper,
                GitHubRepo,
                ResearchCollectionResult,
            )

            # Verify they can be imported
            assert ArxivPaper is not None
            assert GitHubRepo is not None
            assert ResearchCollectionResult is not None
