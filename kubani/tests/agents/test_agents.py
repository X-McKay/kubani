"""Tests for all extracted agents."""

import pytest


class TestAgentImports:
    """Test that all agents can be imported."""

    def test_import_event_classifier(self):
        """Test EventClassifierAgent import."""
        from kubani.agents.event_classifier import EventClassifierAgent

        assert EventClassifierAgent is not None

    def test_import_remediator(self):
        """Test RemediatorAgent import."""
        from kubani.agents.remediator import RemediatorAgent

        assert RemediatorAgent is not None

    def test_import_skill_learner(self):
        """Test SkillLearnerAgent import."""
        from kubani.agents.skill_learner import SkillLearnerAgent

        assert SkillLearnerAgent is not None

    def test_import_feed_collector(self):
        """Test FeedCollectorAgent import."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        assert FeedCollectorAgent is not None

    def test_import_content_analyst(self):
        """Test ContentAnalystAgent import."""
        from kubani.agents.content_analyst import ContentAnalystAgent

        assert ContentAnalystAgent is not None

    def test_import_digest_publisher(self):
        """Test DigestPublisherAgent import."""
        from kubani.agents.digest_publisher import DigestPublisherAgent

        assert DigestPublisherAgent is not None

    def test_import_research_collector(self):
        """Test ResearchCollectorAgent import."""
        from kubani.agents.research_collector import ResearchCollectorAgent

        assert ResearchCollectorAgent is not None

    def test_import_research_analyst(self):
        """Test ResearchAnalystAgent import."""
        from kubani.agents.research_analyst import ResearchAnalystAgent

        assert ResearchAnalystAgent is not None

    def test_import_trend_analyst(self):
        """Test TrendAnalystAgent import."""
        from kubani.agents.trend_analyst import TrendAnalystAgent

        assert TrendAnalystAgent is not None


class TestAgentInstantiation:
    """Test that all agents can be instantiated."""

    def test_event_classifier_instantiation(self):
        """Test EventClassifierAgent can be created."""
        from kubani.agents.event_classifier import EventClassifierAgent

        agent = EventClassifierAgent()
        assert agent is not None
        assert agent.name == "event-classifier"

    def test_remediator_instantiation(self):
        """Test RemediatorAgent can be created."""
        from kubani.agents.remediator import RemediatorAgent

        agent = RemediatorAgent()
        assert agent is not None
        assert agent.name == "remediator"

    def test_skill_learner_instantiation(self):
        """Test SkillLearnerAgent can be created."""
        from kubani.agents.skill_learner import SkillLearnerAgent

        agent = SkillLearnerAgent()
        assert agent is not None
        assert agent.name == "skill-learner"

    def test_feed_collector_instantiation(self):
        """Test FeedCollectorAgent can be created."""
        from kubani.agents.feed_collector import FeedCollectorAgent

        agent = FeedCollectorAgent()
        assert agent is not None
        assert agent.name == "feed-collector"

    def test_content_analyst_instantiation(self):
        """Test ContentAnalystAgent can be created."""
        from kubani.agents.content_analyst import ContentAnalystAgent

        agent = ContentAnalystAgent()
        assert agent is not None
        assert agent.name == "content-analyst"

    def test_digest_publisher_instantiation(self):
        """Test DigestPublisherAgent can be created."""
        from kubani.agents.digest_publisher import DigestPublisherAgent

        agent = DigestPublisherAgent()
        assert agent is not None
        assert agent.name == "digest-publisher"

    def test_research_collector_instantiation(self):
        """Test ResearchCollectorAgent can be created."""
        from kubani.agents.research_collector import ResearchCollectorAgent

        agent = ResearchCollectorAgent()
        assert agent is not None
        assert agent.name == "research-collector"

    def test_research_analyst_instantiation(self):
        """Test ResearchAnalystAgent can be created."""
        from kubani.agents.research_analyst import ResearchAnalystAgent

        agent = ResearchAnalystAgent()
        assert agent is not None
        assert agent.name == "research-analyst"

    def test_trend_analyst_instantiation(self):
        """Test TrendAnalystAgent can be created."""
        from kubani.agents.trend_analyst import TrendAnalystAgent

        agent = TrendAnalystAgent()
        assert agent is not None
        assert agent.name == "trend-analyst"


class TestAgentProperties:
    """Test agent property access."""

    def test_agent_has_config(self):
        """Test agent loads config."""
        from kubani.agents.event_classifier import EventClassifierAgent

        agent = EventClassifierAgent()
        assert agent.config is not None
        assert isinstance(agent.config, dict)

    def test_agent_has_prompt(self):
        """Test agent loads prompt."""
        from kubani.agents.event_classifier import EventClassifierAgent

        agent = EventClassifierAgent()
        assert agent.prompt is not None
        assert isinstance(agent.prompt, str)
        assert len(agent.prompt) > 0

    def test_agent_has_version(self):
        """Test agent has version."""
        from kubani.agents.event_classifier import EventClassifierAgent

        agent = EventClassifierAgent()
        assert agent.version is not None

    def test_agent_has_description(self):
        """Test agent has description."""
        from kubani.agents.event_classifier import EventClassifierAgent

        agent = EventClassifierAgent()
        assert agent.description is not None


class TestBaseAgentAbstract:
    """Test KubaniAgent abstract requirements."""

    def test_cannot_instantiate_base(self):
        """Test that KubaniAgent cannot be directly instantiated."""
        from kubani.agents._base import KubaniAgent

        with pytest.raises(TypeError):
            KubaniAgent()

    def test_subclass_must_implement_on_skill_complete(self):
        """Test that subclass must implement on_skill_complete."""
        from kubani.agents._base import KubaniAgent

        class IncompleteAgent(KubaniAgent):
            AGENT_DIR = None

        with pytest.raises(TypeError):
            IncompleteAgent()
