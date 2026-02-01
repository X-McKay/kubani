"""Tests for skills-centric DigestPublisherAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestDigestPublisherSkills:
    """Test DigestPublisherAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """DigestPublisherAgent should inherit from SkillsOrchestrator."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents._base import SkillsOrchestrator
            from kubani.agents.digest_publisher import DigestPublisherAgent
            assert issubclass(DigestPublisherAgent, SkillsOrchestrator)

    def test_discovers_publishing_skills(self):
        """Agent should discover news/publishing skills."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.digest_publisher import DigestPublisherAgent
            DigestPublisherAgent()  # Instantiate to trigger skill discovery

            # Verify it filters by news domain and publishing category
            call_args = mock.call_args
            assert call_args.kwargs.get('domain') == 'news'
            assert call_args.kwargs.get('category') == 'publishing'

    def test_has_compose_methods(self):
        """Agent should have digest composition methods."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.digest_publisher import DigestPublisherAgent
            agent = DigestPublisherAgent()
            assert hasattr(agent, 'compose_digest')
            assert callable(agent.compose_digest)
            assert hasattr(agent, 'compose_executive_digest')
            assert callable(agent.compose_executive_digest)

    def test_has_publish_methods(self):
        """Agent should have publishing methods."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.digest_publisher import DigestPublisherAgent
            agent = DigestPublisherAgent()
            assert hasattr(agent, 'publish_to_discord')
            assert callable(agent.publish_to_discord)
            assert hasattr(agent, 'compose_and_publish')
            assert callable(agent.compose_and_publish)
            assert hasattr(agent, 'publish_breaking')
            assert callable(agent.publish_breaking)

    @pytest.mark.asyncio
    async def test_compose_digest_generates_task_prompt(self):
        """compose_digest() should generate appropriate task prompt."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.digest_publisher import DigestPublisherAgent
            agent = DigestPublisherAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"headline_summary": "Test summary"}')

            articles = [{"title": "Test Article", "url": "https://example.com"}]
            trends = [{"topic": "AI", "status": "hot"}]
            await agent.compose_digest(articles, trends)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert 'compose' in prompt.lower() or 'digest' in prompt.lower()

    @pytest.mark.asyncio
    async def test_compose_and_publish_runs_pipeline(self):
        """compose_and_publish() should compose and publish the digest."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.digest_publisher import DigestPublisherAgent
            agent = DigestPublisherAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(return_value='{"success": true, "message_id": "123"}')

            articles = [{"title": "Test", "url": "https://example.com"}]
            trends = [{"topic": "AI", "status": "hot"}]
            result = await agent.compose_and_publish(articles, trends)

            # Verify result structure
            assert hasattr(result, 'success')

    def test_exports_dataclasses(self):
        """Agent module should export required dataclasses."""
        with patch('kubani.agents._base.skills_orchestrator.discover_kubani_skills') as mock:
            mock.return_value = []
            from kubani.agents.digest_publisher import (
                ExecutiveDigest,
                NewsDigest,
                PublishResult,
            )
            # Verify they can be imported
            assert PublishResult is not None
            assert NewsDigest is not None
            assert ExecutiveDigest is not None
