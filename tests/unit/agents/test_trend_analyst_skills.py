"""Tests for skills-centric TrendAnalystAgent."""

from unittest.mock import AsyncMock, patch

import pytest


class TestTrendAnalystSkills:
    """Test TrendAnalystAgent with skills-centric architecture."""

    def test_inherits_skills_orchestrator(self):
        """TrendAnalystAgent should inherit from SkillsOrchestrator."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents._base import SkillsOrchestrator
            from kubani.agents.trend_analyst import TrendAnalystAgent

            assert issubclass(TrendAnalystAgent, SkillsOrchestrator)

    def test_discovers_diagnostic_skills(self):
        """Agent should filter by news/diagnostic domain and category."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.trend_analyst import TrendAnalystAgent

            agent = TrendAnalystAgent()
            assert agent.SKILLS_DOMAIN == "news"
            assert agent.SKILLS_CATEGORY == "diagnostic"

    def test_has_analyze_trends_method(self):
        """Agent should have analyze_trends method."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.trend_analyst import TrendAnalystAgent

            agent = TrendAnalystAgent()
            assert hasattr(agent, "analyze_trends")
            assert callable(agent.analyze_trends)

    @pytest.mark.asyncio
    async def test_analyze_trends_generates_task_prompt(self):
        """analyze_trends() should generate appropriate task prompt."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.trend_analyst import TrendAnalystAgent

            agent = TrendAnalystAgent()

            # Mock the agent.run method
            agent.run = AsyncMock(
                return_value='{"trends": [], "emerging_topics": [], "declining_topics": [], "summary": "No trends"}'
            )

            current_entities = {"ai": 5, "llm": 3}
            historical_data = {"ai": 3, "llm": 2}
            await agent.analyze_trends(current_entities, historical_data)

            # Verify run was called with a task prompt
            agent.run.assert_called_once()
            prompt = agent.run.call_args[0][0]
            assert "trend" in prompt.lower() or "analyze" in prompt.lower()

    def test_exports_dataclasses(self):
        """Agent module should export required dataclasses."""
        with patch("kubani.agents._base.skills_orchestrator.load_skills_from_filesystem") as mock:
            mock.return_value = []
            from kubani.agents.trend_analyst import (
                EntityTrend,
                TrendAnalysis,
                TrendAnalystAgent,
            )

            # Verify they can be imported (use TrendAnalystAgent to silence F401)
            assert TrendAnalystAgent is not None
            assert EntityTrend is not None
            assert TrendAnalysis is not None

    @pytest.mark.asyncio
    async def test_on_skill_complete_records_outcome(self):
        """on_skill_complete() should record outcomes for learning."""
        with patch(
            "kubani.agents._base.skills_orchestrator.load_skills_from_filesystem"
        ) as mock_discover:
            mock_discover.return_value = []

            from kubani.agents.trend_analyst import TrendAnalystAgent

            agent = TrendAnalystAgent()

            # Mock record_outcome
            agent.record_outcome = AsyncMock()

            result = {"trends": [{"entity": "ai", "velocity_class": "rising"}]}
            await agent.on_skill_complete("analyze-trends-historical", result)

            agent.record_outcome.assert_called_once()
            call_args = agent.record_outcome.call_args
            assert call_args[0][0] == "analyze-trends-historical"
            assert call_args[1].get("success") is True
