"""Tests for Learning System Syndicate."""

from unittest.mock import AsyncMock, patch

import pytest

from kubani.agents.critic import CriticAgent
from kubani.agents.reflection import ReflectionAgent
from kubani.agents.skill_synthesizer import SkillSynthesizerAgent
from kubani.syndicates.learning_system import LearningSystemSyndicate


class TestLearningSystemSyndicate:
    """Tests for LearningSystemSyndicate."""

    def test_create_syndicate(self):
        """Test syndicate creation."""
        syndicate = LearningSystemSyndicate()
        assert syndicate.name == "learning-system"
        assert syndicate.description is not None

    def test_agents_list(self):
        """Test that all agents are registered."""
        assert len(LearningSystemSyndicate.agents) == 3

        agent_types = LearningSystemSyndicate.agents
        assert CriticAgent in agent_types
        assert ReflectionAgent in agent_types
        assert SkillSynthesizerAgent in agent_types

    def test_get_agent_by_class(self):
        """Test getting agents by class."""
        syndicate = LearningSystemSyndicate()

        critic = syndicate.get_agent(CriticAgent)
        assert isinstance(critic, CriticAgent)

        reflection = syndicate.get_agent(ReflectionAgent)
        assert isinstance(reflection, ReflectionAgent)

        synthesizer = syndicate.get_agent(SkillSynthesizerAgent)
        assert isinstance(synthesizer, SkillSynthesizerAgent)

    def test_agent_singleton(self):
        """Test that agents are singletons within syndicate."""
        syndicate = LearningSystemSyndicate()

        critic1 = syndicate.get_agent(CriticAgent)
        critic2 = syndicate.get_agent(CriticAgent)

        assert critic1 is critic2

    def test_config_loaded(self):
        """Test that config is loaded from config.yaml."""
        syndicate = LearningSystemSyndicate()

        # Should have a config dict
        assert isinstance(syndicate.config, dict)

    @pytest.mark.asyncio
    async def test_stop(self):
        """Test syndicate stop."""
        syndicate = LearningSystemSyndicate()
        syndicate._running = True

        with patch("kubani.syndicates._base.syndicate.get_event_bus") as mock_get_bus:
            mock_bus = AsyncMock()
            mock_get_bus.return_value = mock_bus

            await syndicate.stop()

        assert syndicate._running is False
