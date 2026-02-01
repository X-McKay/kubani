"""Tests for skills-centric ContentAnalystAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestContentAnalystSkills:
    """Test ContentAnalystAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """ContentAnalystAgent should inherit from SkillsOrchestrator."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents._base import SkillsOrchestrator
            from kubani.agents.content_analyst import ContentAnalystAgent
            assert issubclass(ContentAnalystAgent, SkillsOrchestrator)

    def test_discovers_analysis_skills(self):
        """Agent should discover news/analysis skills."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.content_analyst import ContentAnalystAgent
            ContentAnalystAgent()  # Instantiate to trigger skill discovery

            # Verify it filters by news domain and analysis category
            call_args = mock.call_args
            assert call_args.kwargs.get('domain') == 'news'
            assert call_args.kwargs.get('category') == 'analysis'

    def test_has_analyze_methods(self):
        """Agent should have analysis methods."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.content_analyst import ContentAnalystAgent
            agent = ContentAnalystAgent()
            assert hasattr(agent, 'analyze_articles')
            assert callable(agent.analyze_articles)
            assert hasattr(agent, 'detect_breaking_news')
            assert callable(agent.detect_breaking_news)
            assert hasattr(agent, 'analyze_trends')
            assert callable(agent.analyze_trends)

    @pytest.mark.asyncio
    async def test_analyze_articles_generates_task_prompt(self):
        """analyze_articles() should generate appropriate task prompt."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.content_analyst import ContentAnalystAgent
            agent = ContentAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"articles": []}')

            articles = [{"title": "Test Article", "url": "https://example.com"}]
            await agent.analyze_articles(articles)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert 'analyze' in prompt.lower() or 'article' in prompt.lower()

    @pytest.mark.asyncio
    async def test_full_analysis_runs_pipeline(self):
        """full_analysis() should run the complete analysis pipeline."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.content_analyst import ContentAnalystAgent
            agent = ContentAnalystAgent()

            # Mock the agent.run method for each call
            agent.run = AsyncMock(return_value='[]')

            articles = [{"title": "Test", "url": "https://example.com"}]
            result = await agent.full_analysis(articles)

            # Verify result structure
            assert hasattr(result, 'processed_articles')
            assert hasattr(result, 'breaking_articles')
            assert hasattr(result, 'trends')

    def test_exports_dataclasses(self):
        """Agent module should export required dataclasses."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.content_analyst import (
                AnalysisResult,
                ProcessedArticle,
                TrendingTopic,
            )
            # Verify they can be imported
            assert ProcessedArticle is not None
            assert TrendingTopic is not None
            assert AnalysisResult is not None
