"""Tests for skills-centric ResearchAnalystAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestResearchAnalystSkills:
    """Test ResearchAnalystAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """ResearchAnalystAgent should inherit from SkillsOrchestrator."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents._base import SkillsOrchestrator
            from kubani.agents.research_analyst import ResearchAnalystAgent

            assert issubclass(ResearchAnalystAgent, SkillsOrchestrator)

    def test_discovers_diagnostic_skills(self):
        """Agent should filter by news/diagnostic domain and category."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()
            assert agent.SKILLS_DOMAIN == "news"
            assert agent.SKILLS_CATEGORY == "diagnostic"

    def test_has_analyze_methods(self):
        """Agent should have analysis methods."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()

            # Paper analysis methods
            assert hasattr(agent, "analyze_paper")
            assert callable(agent.analyze_paper)
            assert hasattr(agent, "analyze_papers_batch")
            assert callable(agent.analyze_papers_batch)

            # Repo analysis methods
            assert hasattr(agent, "analyze_repo")
            assert callable(agent.analyze_repo)
            assert hasattr(agent, "analyze_repos_batch")
            assert callable(agent.analyze_repos_batch)

    @pytest.mark.asyncio
    async def test_analyze_paper_generates_task_prompt(self):
        """analyze_paper() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(
                return_value='{"research_type": "new_method", "main_claim": "test"}'
            )

            paper = {
                "arxiv_id": "2601.12345",
                "title": "Test Paper",
                "authors": ["Author One"],
                "abstract": "This is a test abstract with enough content to pass validation. "
                * 5,  # >100 chars
                "categories": ["cs.AI"],
            }
            await agent.analyze_paper(paper)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "paper" in prompt.lower() or "analyze" in prompt.lower()

    @pytest.mark.asyncio
    async def test_analyze_repo_generates_task_prompt(self):
        """analyze_repo() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(
                return_value='{"category": "library", "spotlight_summary": "test"}'
            )

            repo = {
                "full_name": "owner/repo-name",
                "name": "repo-name",
                "description": "A test repository with sufficient description",
                "stars": 1000,
                "forks": 100,
                "language": "Python",
                "topics": ["ml"],
                "pushed_at": "2026-01-26",
            }
            await agent.analyze_repo(repo)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "repo" in prompt.lower() or "analyze" in prompt.lower()

    @pytest.mark.asyncio
    async def test_analyze_papers_batch(self):
        """analyze_papers_batch() should analyze multiple papers."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"research_type": "new_method"}')

            papers = [
                {
                    "arxiv_id": "2601.001",
                    "title": "Paper 1",
                    "authors": ["A"],
                    "abstract": "Long abstract one " * 10,
                },
                {
                    "arxiv_id": "2601.002",
                    "title": "Paper 2",
                    "authors": ["B"],
                    "abstract": "Long abstract two " * 10,
                },
            ]
            results = await agent.analyze_papers_batch(papers)

            # Should call run twice, once per paper
            assert agent.run.call_count == 2
            assert len(results) == 2

    @pytest.mark.asyncio
    async def test_analyze_repos_batch(self):
        """analyze_repos_batch() should analyze multiple repos."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.research_analyst import ResearchAnalystAgent

            agent = ResearchAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"category": "library"}')

            repos = [
                {
                    "full_name": "a/repo1",
                    "name": "repo1",
                    "description": "Description one here",
                    "stars": 100,
                },
                {
                    "full_name": "b/repo2",
                    "name": "repo2",
                    "description": "Description two here",
                    "stars": 200,
                },
            ]
            results = await agent.analyze_repos_batch(repos)

            # Should call run twice, once per repo
            assert agent.run.call_count == 2
            assert len(results) == 2

    def test_exports_dataclasses(self):
        """Agent module should export required dataclasses."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.research_analyst import (
                PaperAnalysis,
                RepoAnalysis,
            )

            # Verify they can be imported
            assert PaperAnalysis is not None
            assert RepoAnalysis is not None
